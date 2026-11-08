import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows to avoid cp1252 UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

from config import EXPORTS_DIR, PROJECT_DIR
from database import (
    get_connection,
    create_tables,
    set_metadata,
    find_movie_by_uri,
    find_movie_by_name_year,
)
from imdb import setup_imdb_ratings
from enrichment import enrich_movie
from export_selector import (
    select_export_folder,
    get_latest_export_folder,
    save_stored_export_folder,
)


def step_1_setup(conn):
    """Step 1:
    - Runs PRAGMA foreign_keys=ON (handled by get_connection)
    - Creates any missing tables, indexes, and active_movies view
    - Ensures IMDb dataset is available, gunzipped, and loaded into imdb_ratings
    """
    print("=" * 60)
    print("STEP 1: Database Setup & IMDb Ratings Initialization")
    print("=" * 60)

    # 1. Create missing tables and view
    create_tables(conn)
    print("[DB] Tables and views verified.")

    # 2. Check / update IMDb ratings dataset
    setup_imdb_ratings(conn)


def step_2_import_csv(conn, csv_path: Path):
    """Step 2:
    - Load the CSV with pandas.
    - Create active_csv_uris set.
    - For each row: query movies by URI, fallback to name + year.
      - If found: compare rating, rated_date, uri; UPDATE if different.
      - If not found: INSERT with fetch_status = 'pending'.
    - After loop: set is_active = 1 for URIs in set, 0 for others.
    - Commit the transaction once.
    """
    print("=" * 60)
    print(f"STEP 2: Importing Letterboxd CSV from {csv_path.name}")
    print("=" * 60)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        return

    if df.empty:
        print("CSV is empty. Skipping Step 2.")
        return

    active_csv_uris = set()
    cursor = conn.cursor()

    inserted_count = 0
    updated_count = 0
    unchanged_count = 0

    for _, row in df.iterrows():
        uri = str(row["Letterboxd URI"]).strip() if pd.notna(row.get("Letterboxd URI")) else ""
        name = str(row["Name"]).strip() if pd.notna(row.get("Name")) else ""
        year = int(row["Year"]) if pd.notna(row.get("Year")) else 0
        rated_date = str(row["Date"]).strip() if pd.notna(row.get("Date")) else ""

        rating_raw = row.get("Rating")
        rating = float(rating_raw) if pd.notna(rating_raw) and str(rating_raw).strip() != "" else None

        active_csv_uris.add(uri)

        # 1. Query by URI
        db_movie = find_movie_by_uri(conn, uri)
        # 2. Fallback to name + year
        if not db_movie:
            db_movie = find_movie_by_name_year(conn, name, year)

        if db_movie:
            movie_id, db_name, db_year, db_rating, db_rated_date, db_uri = db_movie

            # Compare rating, rated_date, and uri
            rating_differs = False
            if rating is None and db_rating is not None:
                rating_differs = True
            elif rating is not None and db_rating is None:
                rating_differs = True
            elif rating is not None and db_rating is not None and abs(rating - db_rating) > 0.001:
                rating_differs = True

            date_differs = (rated_date != (db_rated_date or ""))
            uri_differs = (uri != (db_uri or ""))

            if rating_differs or date_differs or uri_differs:
                cursor.execute("""
                    UPDATE movies
                    SET rating = ?, rated_date = ?, uri = ?
                    WHERE movie_id = ?
                """, (rating, rated_date, uri, movie_id))
                updated_count += 1
            else:
                unchanged_count += 1
        else:
            cursor.execute("""
                INSERT INTO movies (name, year, rating, rated_date, uri, fetch_status, is_active)
                VALUES (?, ?, ?, ?, ?, 'pending', 1)
            """, (name, year, rating, rated_date, uri))
            inserted_count += 1

    # After loop: update is_active for all movies using temp table
    cursor.execute("CREATE TEMP TABLE IF NOT EXISTS temp_active_uris (uri TEXT PRIMARY KEY);")
    cursor.execute("DELETE FROM temp_active_uris;")
    cursor.executemany("INSERT INTO temp_active_uris VALUES (?)", [(u,) for u in active_csv_uris])

    cursor.execute("""
        UPDATE movies
        SET is_active = CASE
            WHEN uri IN (SELECT uri FROM temp_active_uris) THEN 1
            ELSE 0
        END;
    """)
    cursor.execute("DROP TABLE temp_active_uris;")

    # Record last_csv_import timestamp
    set_metadata(conn, "last_csv_import", datetime.now().isoformat())

    # Single commit after the loop and is_active update
    conn.commit()

    print(f"[OK] CSV processed: {inserted_count} inserted, {updated_count} updated, {unchanged_count} unchanged.")
    print(f"[OK] {len(active_csv_uris)} movies marked active.\n")


def step_3_tmdb_fetch(conn):
    """Step 3:
    - For every row with fetch_status pending or failed:
      - Enrich movie using enrich_movie helper (TMDb search/details, collection, people, countries, companies)
      - Sets fetch_status to ok, not_found, or failed.
    """
    print("=" * 60)
    print("STEP 3: TMDb Metadata Enrichment & Link Tables Population")
    print("=" * 60)

    cursor = conn.cursor()
    cursor.execute("""
        SELECT movie_id, name, year, tmdb_id
        FROM movies
        WHERE fetch_status IN ('pending', 'failed')
            AND is_active = 1
        ORDER BY movie_id ASC
    """)
    pending_movies = cursor.fetchall()
    total = len(pending_movies)

    if total == 0:
        print("[OK] All movies are updated. Nothing to fetch.\n")
        return

    print(f"Found {total} movies to fetch.\n")

    success_count = 0
    not_found_count = 0
    failed_count = 0

    for i, (movie_id, name, year, existing_tmdb_id) in enumerate(pending_movies, start=1):
        print(f"[{i}/{total}] '{name}' ({year})...", end=" ", flush=True)

        try:
            status = enrich_movie(conn, movie_id, name, year, existing_tmdb_id=existing_tmdb_id)
            if status == "ok":
                success_count += 1
                print("[OK]")
            elif status == "not_found":
                not_found_count += 1
                print("[NOT FOUND on TMDb]")
            else:
                failed_count += 1
                print(f"[{status.upper()}]")
        except Exception as e:
            print(f"[FAILED] Error: {e}")
            cursor.execute("UPDATE movies SET fetch_status = 'failed' WHERE movie_id = ?", (movie_id,))
            conn.commit()
            failed_count += 1

        # Rate limit safety delay
        time.sleep(0.1)

    print("\n" + "=" * 60)
    print(f"Step 3 Complete: {success_count} ok, {not_found_count} not found, {failed_count} failed.")
    print("=" * 60 + "\n")


def launch_dashboard():
    """Launch the Streamlit interactive dashboard in browser."""
    print("Launching Streamlit dashboard...")
    dashboard_app = PROJECT_DIR / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_app)])


def main():
    parser = argparse.ArgumentParser(description="Letterboxd Data Analyzer - Ingestion Pipeline")
    parser.add_argument("--folder", help="Specific export folder name or absolute path")
    parser.add_argument("--latest", action="store_true", help="Automatically use the latest export folder without GUI prompt")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit dashboard immediately after run")
    args = parser.parse_args()

    conn = get_connection()

    # Step 1: Database Setup, Schema & IMDb Ratings
    step_1_setup(conn)

    # Determine export folder
    export_folder = None
    if args.folder:
        custom_path = Path(args.folder)
        if not custom_path.is_absolute():
            custom_path = EXPORTS_DIR / args.folder
        if not custom_path.exists():
            print(f"Error: Specified export folder not found: {custom_path}")
            sys.exit(1)
        export_folder = custom_path
        save_stored_export_folder(conn, export_folder)
    elif args.latest:
        export_folder = get_latest_export_folder()
        if not export_folder:
            print("Error: No export folder found.")
            sys.exit(1)
        save_stored_export_folder(conn, export_folder)
    else:
        # Prompt user using Tkinter GUI
        export_folder = select_export_folder(conn, interactive=True)

    ratings_csv = export_folder / "ratings.csv"
    if not ratings_csv.exists():
        print(f"Error: 'ratings.csv' not found in {export_folder}")
        sys.exit(1)

    try:
        # Step 2: Letterboxd CSV Import with active URIs
        step_2_import_csv(conn, ratings_csv)

        # Step 3: TMDb API Enrichment & Link Tables
        step_3_tmdb_fetch(conn)

    finally:
        conn.close()

    # If --dashboard flag requested, launch streamlit
    if args.dashboard:
        launch_dashboard()


if __name__ == "__main__":
    main()

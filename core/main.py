import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd         # External Library

from config import PROJECT_DIR
from database import (
    get_connection,
    create_tables,
    set_metadata,
    find_movie_by_uri,
    find_movie_by_name_year,
)
from imdb import setup_imdb_ratings
from tmdb import search_movie, get_movie_details, get_collection_details
from localization import get_country_name, get_language_name
from stats import print_stats_summary

# Force UTF-8 stdout/stderr on Windows to avoid cp1252 UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def find_export_folder(folder_name=None):
    """Find the Letterboxd export folder to process."""
    if folder_name:
        path = PROJECT_DIR / folder_name
        if not path.exists():
            print(f"Error: Export folder not found: {path}")
            sys.exit(1)
        return path

    folders = sorted(
        [f for f in PROJECT_DIR.iterdir() if f.is_dir()],
        reverse=True
    )
    if not folders:
        print(f"Error: No export folders found in {PROJECT_DIR}")
        sys.exit(1)

    return folders[0]


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
      - Search TMDb (retry with year ±1, exact title match preferred, then popularity)
      - Call GET /movie/{id}?append_to_response=credits
      - If collection_id isn't in collections or fetched_at < release date/year:
        - Fetch collection and insert BEFORE movie row
      - Fill link tables (movie_cast, movie_directors, movie_genres, movie_countries, people)
      - UPDATE the existing movies row (do not insert a second row)
      - Set fetch_status to ok, not_found, or failed.
    """
    print("=" * 60)
    print("STEP 3: TMDb Metadata Enrichment & Link Tables Population")
    print("=" * 60)

    cursor = conn.cursor()
    cursor.execute("""
        SELECT movie_id, name, year, uri
        FROM movies
        WHERE fetch_status IN ('pending', 'failed')
        ORDER BY movie_id ASC
    """)
    pending_movies = cursor.fetchall()
    total = len(pending_movies)

    if total == 0:
        print("[OK] All movies already have metadata. No pending or failed movies found.\n")
        return

    print(f"Found {total} movies with fetch_status of pending or failed.\n")
    today_str = datetime.now().strftime("%Y-%m-%d")

    success_count = 0
    not_found_count = 0
    failed_count = 0

    for i, (movie_id, name, year, uri) in enumerate(pending_movies, start=1):
        print(f"[{i}/{total}] '{name}' ({year})...", end=" ", flush=True)

        try:
            # 1. Search TMDb
            tmdb_id = search_movie(name, year)
            if not tmdb_id:
                print("NOT FOUND on TMDb.")
                cursor.execute("UPDATE movies SET fetch_status = 'not_found' WHERE movie_id = ?", (movie_id,))
                conn.commit()
                not_found_count += 1
                continue

            # 2. Get movie details with credits
            details = get_movie_details(tmdb_id)

            imdb_id = details.get("imdb_id")
            runtime = details.get("runtime")
            original_language = details.get("original_language")
            poster_path = details.get("poster_path")
            backdrop_path = details.get("backdrop_path")
            origin_country = details.get("origin_country") or []
            genres = details.get("genres") or []

            # 3. Collection handling
            collection_info = details.get("belongs_to_collection")
            collection_id = collection_info.get("id") if collection_info else None

            if collection_id:
                cursor.execute("SELECT fetched_at FROM collections WHERE collection_id = ?", (collection_id,))
                coll_row = cursor.fetchone()

                movie_release = details.get("release_date") or str(year)
                needs_coll_fetch = False

                if not coll_row:
                    needs_coll_fetch = True
                else:
                    fetched_at = coll_row[0] or ""
                    # If fetched_at < release_date (or year)
                    if fetched_at[:10] < movie_release[:10]:
                        needs_coll_fetch = True

                if needs_coll_fetch:
                    try:
                        coll_data = get_collection_details(collection_id)
                        coll_name = coll_data.get("name") or collection_info.get("name") or "Collection"
                        coll_poster = coll_data.get("poster_path")
                        coll_backdrop = coll_data.get("backdrop_path")
                        parts = coll_data.get("parts") or []

                        # Count released parts only
                        released_parts = [
                            p for p in parts
                            if p.get("release_date") and p.get("release_date").strip() <= today_str
                        ]
                        total_movies = len(released_parts)
                        coll_fetched_at = datetime.now().isoformat()

                        # Insert collection BEFORE movie row that references it
                        cursor.execute("""
                            INSERT INTO collections (
                                collection_id, collection_name, total_movies,
                                poster_path, backdrop_path, fetched_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(collection_id) DO UPDATE SET
                                collection_name = excluded.collection_name,
                                total_movies = excluded.total_movies,
                                poster_path = excluded.poster_path,
                                backdrop_path = excluded.backdrop_path,
                                fetched_at = excluded.fetched_at;
                        """, (collection_id, coll_name, total_movies, coll_poster, coll_backdrop, coll_fetched_at))
                        conn.commit()
                    except Exception as ce:
                        print(f" [Collection fetch note: {ce}]", end="", flush=True)

            # 4. Fill people and link tables
            credits = details.get("credits") or {}
            raw_cast = credits.get("cast") or []
            crew = credits.get("crew") or []

            # Cast: first 25 by billing order
            top_cast = raw_cast[:25]
            directors = [c for c in crew if c.get("job") == "Director"]

            # Insert people
            for p in top_cast + directors:
                pid = p.get("id")
                pname = p.get("name")
                profile = p.get("profile_path")
                if pid and pname:
                    cursor.execute("""
                        INSERT INTO people (person_id, name, profile_paths)
                        VALUES (?, ?, ?)
                        ON CONFLICT(person_id) DO UPDATE SET
                            name = excluded.name,
                            profile_paths = COALESCE(excluded.profile_paths, people.profile_paths);
                    """, (pid, pname, profile))

            # movie_cast
            cursor.execute("DELETE FROM movie_cast WHERE movie_id = ?", (movie_id,))
            for idx, member in enumerate(top_cast):
                pid = member.get("id")
                order = member.get("order", idx)
                if pid:
                    cursor.execute("""
                        INSERT OR REPLACE INTO movie_cast (movie_id, person_id, billing_order)
                        VALUES (?, ?, ?);
                    """, (movie_id, pid, order))

            # movie_directors
            cursor.execute("DELETE FROM movie_directors WHERE movie_id = ?", (movie_id,))
            for d in directors:
                pid = d.get("id")
                if pid:
                    cursor.execute("""
                        INSERT OR REPLACE INTO movie_directors (movie_id, person_id)
                        VALUES (?, ?);
                    """, (movie_id, pid))

            # movie_genres
            cursor.execute("DELETE FROM movie_genres WHERE movie_id = ?", (movie_id,))
            for g in genres:
                gid = g.get("id")
                gname = g.get("name")
                if gid and gname:
                    cursor.execute("""
                        INSERT OR REPLACE INTO movie_genres (movie_id, genre_id, genre_name)
                        VALUES (?, ?, ?);
                    """, (movie_id, gid, gname))

            # movie_countries (origin_country, not production_countries)
            cursor.execute("DELETE FROM movie_countries WHERE movie_id = ?", (movie_id,))
            for code in origin_country:
                if code:
                    cursor.execute("""
                        INSERT OR REPLACE INTO movie_countries (movie_id, country_code)
                        VALUES (?, ?);
                    """, (movie_id, str(code).strip()))

            # 5. UPDATE the existing movies row
            cursor.execute("""
                UPDATE movies SET
                    tmdb_id = ?,
                    imdb_id = ?,
                    runtime = ?,
                    original_language = ?,
                    poster_path = ?,
                    backdrop_path = ?,
                    collection_id = ?,
                    fetch_status = 'ok'
                WHERE movie_id = ?;
            """, (tmdb_id, imdb_id, runtime, original_language, poster_path, backdrop_path, collection_id, movie_id))
            conn.commit()

            success_count += 1
            print(f"[OK] TMDb ID {tmdb_id}")

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


def main():
    # --- Configuration ---
    # Choose export folder:
    # 1. Test folder with 10 movies:
    # export_folder_name = "letterboxd-tharu99-2026-10-30-17-31-utc"
    # 2. Or full folder with 341 movies:
    export_folder_name = "letterboxd-tharu99-2026-10-29-17-31-utc"
    # 3. Or None for the most recent export:
    # export_folder_name = None

    export_folder = find_export_folder(export_folder_name)
    ratings_csv = export_folder / "ratings.csv"
    print(f"Selected export: {export_folder.name}\n")

    conn = get_connection()

    try:
        # Step 1: Database Setup, Schema & IMDb Ratings
        step_1_setup(conn)

        # Step 2: Letterboxd CSV Import with active URIs
        step_2_import_csv(conn, ratings_csv)

        # Step 3: TMDb API Enrichment & Link Tables
        step_3_tmdb_fetch(conn)

        # Step 4 & 5 Preview: Display Dashboard from active_movies
        print_stats_summary()

    finally:
        conn.close()


if __name__ == "__main__":
    main()

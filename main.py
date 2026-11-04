import csv
import sys
import time

from config import EXPORTS_DIR
from database import (
    get_connection,
    create_tables,
    movie_exists,
    find_tmdb_id_by_uri,
    find_tmdb_id_by_title,
    save_movie,
    save_rating,
)
from movie import Movie
from tmdb import search_movie, get_movie_details
from imdb import imdb_manager, get_imdb_rating


def find_export_folder(folder_name=None):
    """Find the Letterboxd export folder to process.

    Parameters
    ----------
    folder_name : str, optional
        Specific export folder name (e.g. 'letterboxd-tharu99-2026-10-30-17-31-utc').
        If None, the most recent export folder is used.

    Returns
    -------
    Path to the export folder.
    """
    if folder_name:
        path = EXPORTS_DIR / folder_name
        if not path.exists():
            print(f"Error: Export folder not found: {path}")
            sys.exit(1)
        return path

    # Find the most recent export folder by name
    folders = sorted(EXPORTS_DIR.iterdir(), reverse=True)
    if not folders:
        print(f"Error: No export folders found in {EXPORTS_DIR}")
        sys.exit(1)

    return folders[0]


def read_ratings(export_folder):
    """Read ratings.csv and return a list of raw movie dicts.

    Returns
    -------
    list[dict]
        Each dict has keys: Date, Name, Year, Letterboxd URI, Rating
    """
    ratings_path = export_folder / "ratings.csv"

    if not ratings_path.exists():
        print(f"Error: ratings.csv not found in {export_folder}")
        sys.exit(1)

    with open(ratings_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def process_movie_row(conn, row):
    """Process a single ratings.csv row:
    1. Resolve TMDb ID (from database cache or TMDb search)
    2. Check if movie already exists in DB - if so, SKIP TMDb API details call
    3. If new, fetch details from TMDb & ratings from IMDb dataset, then save to movies table
    4. Save the user's rating into the ratings table (with tmdb_id as foreign key)

    Parameters
    ----------
    conn : sqlite3.Connection
    row : dict
        A row from ratings.csv with keys: Date, Name, Year, Letterboxd URI, Rating

    Returns
    -------
    bool: True if processed successfully, False otherwise.
    """
    name = row["Name"]
    year = int(row["Year"])
    rating_date = row["Date"]
    letterboxd_uri = row["Letterboxd URI"]
    user_rating = float(row["Rating"]) if row.get("Rating") else None

    # Step 1: Check if TMDb ID is already known in our database
    tmdb_id = find_tmdb_id_by_uri(conn, letterboxd_uri)
    if not tmdb_id:
        tmdb_id = find_tmdb_id_by_title(conn, name, year)

    # If not found in DB cache, search via TMDb API
    if not tmdb_id:
        print(f"  Searching TMDb API for '{name}' ({year})...", end=" ", flush=True)
        tmdb_id = search_movie(name, year)
        if tmdb_id is None:
            print("NOT FOUND")
            return False
        print(f"found (TMDb ID: {tmdb_id})")

    # Step 2: Check if canonical movie details already exist in movies table
    if movie_exists(conn, tmdb_id):
        print(f"  [DB CACHE] Movie metadata already in DB (TMDb ID: {tmdb_id}). Skipping TMDb API call.")
    else:
        # Fetch metadata from TMDb API
        print(f"  [API] Fetching TMDb details for ID {tmdb_id}...", end=" ", flush=True)
        tmdb_data = get_movie_details(tmdb_id)
        imdb_id = tmdb_data.get("imdb_id")
        print("done.")

        # Fetch IMDb rating and votes from local IMDb dataset
        imdb_data = get_imdb_rating(imdb_id, conn=conn) if imdb_id else None
        if imdb_data:
            print(f"  [IMDb] Found rating: {imdb_data['imdb_rating']}/10 ({imdb_data['imdb_votes']:,} votes)")
        else:
            print(f"  [IMDb] No IMDb rating found for {imdb_id or 'unknown ID'}")

        # Construct Movie and save to movies table (tmdb_id as primary key)
        movie = Movie(
            name=name,
            year=year,
            letterboxd_uri=letterboxd_uri,
            rating_date=rating_date,
            user_rating=user_rating,
        )
        movie.update_metadata(tmdb_data, imdb_data)
        save_movie(conn, movie)
        print(f"  [OK] Saved movie metadata to 'movies' table.")

    # Step 3: Save / update the rating in ratings table (tmdb_id as foreign key)
    save_rating(
        conn=conn,
        letterboxd_uri=letterboxd_uri,
        tmdb_id=tmdb_id,
        name=name,
        year=year,
        rating_date=rating_date,
        user_rating=user_rating
    )
    print(f"  [OK] Linked rating to TMDb ID {tmdb_id} in 'ratings' table.\n")
    return True


def main():
    # --- Configuration ---
    # Set to a specific folder name to use that export, or None for the latest
    export_folder_name = "letterboxd-tharu99-2026-10-30-17-31-utc"  # test data (9 movies)
    # export_folder_name = "letterboxd-tharu99-2026-10-29-17-31-utc"  # full data (341 movies)
    # export_folder_name = None  # use the latest export

    export_folder = find_export_folder(export_folder_name)
    print(f"Using export folder: {export_folder.name}\n")

    # Set up database
    conn = get_connection()
    create_tables(conn)

    # Ensure IMDb dataset is available and up-to-date (downloads if missing or >30 days old)
    print("Checking IMDb official dataset...")
    imdb_manager.ensure_dataset(conn=conn)
    # Preload IMDb cache into memory once for lightning-fast lookups
    imdb_manager.load_cache()
    print()

    # Read ratings from CSV
    ratings = read_ratings(export_folder)
    total = len(ratings)
    print(f"Found {total} rated movies in ratings.csv\n")

    # Process each movie
    success = 0
    failed = 0

    for i, row in enumerate(ratings, start=1):
        print(f"[{i}/{total}] {row['Name']} ({row['Year']})")

        try:
            if process_movie_row(conn, row):
                success += 1
            else:
                failed += 1
                print(f"  [SKIP] Could not process movie.\n")

        except Exception as e:
            failed += 1
            print(f"  [ERROR] {e}\n")

        # Small delay between API calls to respect rate limits
        time.sleep(0.15)

    conn.close()

    # Summary
    print("=" * 40)
    print(f"Processing complete!")
    print(f"  Successful: {success}/{total}")
    print(f"  Failed:     {failed}/{total}")


if __name__ == "__main__":
    main()

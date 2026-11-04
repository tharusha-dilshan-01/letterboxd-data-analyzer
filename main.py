import csv
import sys
import time

from config import EXPORTS_DIR
from database import get_connection, create_tables, upsert_movie
from movie import Movie
from tmdb import search_movie, get_movie_details
from omdb import get_imdb_rating


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

    # Find the most recent export folder by name (they sort chronologically)
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


def process_movie(row):
    """Create a Movie from a ratings.csv row and enrich it with API data.

    Parameters
    ----------
    row : dict
        A row from ratings.csv with keys: Date, Name, Year, Letterboxd URI, Rating

    Returns
    -------
    Movie or None if the movie could not be found on TMDb.
    """
    name = row["Name"]
    year = int(row["Year"])
    rating_date = row["Date"]
    letterboxd_uri = row["Letterboxd URI"]
    user_rating = float(row["Rating"]) if row["Rating"] else None

    print(f"  Searching TMDb for: {name} ({year})...", end=" ")
    movie_id = search_movie(name, year)

    if movie_id is None:
        print("NOT FOUND")
        return None

    print(f"found (TMDb ID: {movie_id})")

    # Initialize Movie with Letterboxd data
    current_movie = Movie(
        name=name,
        year=year,
        letterboxd_uri=letterboxd_uri,
        rating_date=rating_date,
        user_rating=user_rating,
    )

    # Fetch detailed metadata from TMDb
    tmdb_data = get_movie_details(movie_id)
    imdb_id = tmdb_data.get("imdb_id")

    # Fetch IMDb rating
    imdb_data = get_imdb_rating(imdb_id) if imdb_id else None

    # Populate all metadata fields
    current_movie.update_metadata(tmdb_data, imdb_data)

    return current_movie


def main():
    # --- Configuration ---
    # Set to a specific folder name to use that export, or None for the latest
    export_folder_name = "letterboxd-tharu99-2026-10-30-17-31-utc"  # test data
    # export_folder_name = "letterboxd-tharu99-2026-10-29-17-31-utc"  # full data
    # export_folder_name = None  # use the latest export

    export_folder = find_export_folder(export_folder_name)
    print(f"Using export folder: {export_folder.name}\n")

    # Read ratings from CSV
    ratings = read_ratings(export_folder)
    total = len(ratings)
    print(f"Found {total} rated movies in ratings.csv\n")

    # Set up database
    conn = get_connection()
    create_tables(conn)

    # Process each movie
    success = 0
    failed = 0

    for i, row in enumerate(ratings, start=1):
        print(f"[{i}/{total}] {row['Name']} ({row['Year']})")

        try:
            movie = process_movie(row)

            if movie:
                upsert_movie(conn, movie)
                success += 1
                print(f"  [OK] Saved to database\n")
            else:
                failed += 1
                print(f"  [SKIP] Not found on TMDb\n")

        except Exception as e:
            failed += 1
            print(f"  [ERROR] {e}\n")

        # Small delay to respect API rate limits
        time.sleep(0.25)

    conn.close()

    # Summary
    print("=" * 40)
    print(f"Processing complete!")
    print(f"  Successful: {success}/{total}")
    print(f"  Failed:     {failed}/{total}")


if __name__ == "__main__":
    main()

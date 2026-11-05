import os
import gzip
import shutil
import time
from datetime import datetime
from pathlib import Path
import requests

from config import (
    IMDB_DIR,
    IMDB_DATASET_URL,
    IMDB_GZ_PATH,
    IMDB_TSV_PATH,
    IMDB_MAX_AGE_DAYS,
)
from database import get_metadata, set_metadata


def gunzip_file(gz_path: Path, tsv_path: Path):
    """Decompress a .tsv.gz file to .tsv using streaming."""
    temp_tsv = tsv_path.with_suffix(".tmp")
    print(f"Gunzipping {gz_path.name} to {tsv_path.name}...", end=" ", flush=True)
    t0 = time.time()
    with gzip.open(gz_path, "rb") as f_in, open(temp_tsv, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
    if tsv_path.exists():
        tsv_path.unlink()
    temp_tsv.rename(tsv_path)
    print(f"done in {time.time() - t0:.2f}s ({tsv_path.stat().st_size / 1024 / 1024:.1f} MB)")


def download_imdb_gz(gz_path: Path):
    """Download IMDb dataset to a temporary file, then rename on success."""
    IMDB_DIR.mkdir(parents=True, exist_ok=True)
    temp_gz = gz_path.with_suffix(".tmp")

    print(f"Downloading IMDb dataset from {IMDB_DATASET_URL}...")
    t0 = time.time()

    response = requests.get(IMDB_DATASET_URL, stream=True, timeout=60)
    response.raise_for_status()

    total_bytes = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024  # 1MB

    with open(temp_gz, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_bytes > 0:
                    pct = (downloaded / total_bytes) * 100
                    print(f"  Progress: {downloaded / 1024 / 1024:.1f} MB / {total_bytes / 1024 / 1024:.1f} MB ({pct:.0f}%)", end="\r")

    # Atomic rename on success
    if gz_path.exists():
        gz_path.unlink()
    temp_gz.rename(gz_path)
    print(f"\n[OK] Downloaded {gz_path.name} in {time.time() - t0:.1f}s")


def load_tsv_to_database(conn, tsv_path: Path):
    """Load the uncompressed TSV file into a staging table, then swap it in as imdb_ratings.
    A failed load will drop the staging table and leave the existing imdb_ratings table intact.
    """
    if not tsv_path.exists():
        raise FileNotFoundError(f"TSV file not found: {tsv_path}")

    print("Loading IMDb TSV into database staging table...", flush=True)
    t0 = time.time()

    cursor = conn.cursor()
    # Create clean staging table
    cursor.execute("DROP TABLE IF EXISTS imdb_ratings_staging;")
    cursor.execute("""
        CREATE TABLE imdb_ratings_staging (
            imdb_id TEXT PRIMARY KEY,
            rating  REAL,
            votes   INTEGER
        );
    """)
    conn.commit()

    batch = []
    batch_size = 50000
    total_loaded = 0

    try:
        with open(tsv_path, "r", encoding="utf-8") as f:
            # Skip header: tconst \t averageRating \t numVotes
            next(f, None)
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    try:
                        batch.append((parts[0], float(parts[1]), int(parts[2])))
                    except ValueError:
                        continue

                    if len(batch) >= batch_size:
                        cursor.executemany("INSERT INTO imdb_ratings_staging VALUES (?, ?, ?)", batch)
                        total_loaded += len(batch)
                        batch = []

            if batch:
                cursor.executemany("INSERT INTO imdb_ratings_staging VALUES (?, ?, ?)", batch)
                total_loaded += len(batch)

        conn.commit()

        # Swap staging table into imdb_ratings atomically
        print(f"Loaded {total_loaded:,} ratings in {time.time() - t0:.2f}s. Swapping tables...", end=" ", flush=True)
        cursor.execute("DROP TABLE IF EXISTS imdb_ratings;")
        cursor.execute("ALTER TABLE imdb_ratings_staging RENAME TO imdb_ratings;")
        conn.commit()
        print("done.")

    except Exception as e:
        conn.rollback()
        # Clean up staging table on failure
        cursor.execute("DROP TABLE IF EXISTS imdb_ratings_staging;")
        conn.commit()
        raise RuntimeError(f"Failed to load IMDb TSV into database: {e}") from e


def setup_imdb_ratings(conn, ask_update_func=None):
    """Step 1 IMDb workflow:
    1. Check if title.ratings.tsv.gz exists locally.
    2. If missing: download, rename, gunzip, and swap into imdb_ratings.
    3. If older than 30 days (imdb_last_updated): ask user. If declined, warn and continue.
    4. If updated or if imdb_ratings is empty, load TSV into staging table and swap.
    """
    last_updated_str = get_metadata(conn, "imdb_last_updated")
    last_updated_dt = None
    if last_updated_str:
        try:
            last_updated_dt = datetime.fromisoformat(last_updated_str)
        except ValueError:
            pass

    # Check if gz exists locally
    gz_exists = IMDB_GZ_PATH.exists()
    tsv_exists = IMDB_TSV_PATH.exists()

    should_download = False

    if not gz_exists:
        print("[IMDb] title.ratings.tsv.gz not found locally. Will download.")
        should_download = True
    else:
        # Check age
        if last_updated_dt is None:
            # Fallback to gz file mtime
            mtime = os.path.getmtime(IMDB_GZ_PATH)
            last_updated_dt = datetime.fromtimestamp(mtime)

        age_days = (datetime.now() - last_updated_dt).days

        if age_days >= IMDB_MAX_AGE_DAYS:
            # Older than 30 days -> ask user
            update_choice = None
            if ask_update_func:
                update_choice = ask_update_func(age_days, last_updated_dt)
            else:
                try:
                    prompt = (
                        f"\n[IMDb] The local IMDb ratings dataset is {age_days} days old "
                        f"(last updated {last_updated_dt.strftime('%Y-%m-%d')}).\n"
                        f"Would you like to download an update now? [y/N]: "
                    )
                    user_input = input(prompt).strip().lower()
                    update_choice = user_input in ("y", "yes")
                except (EOFError, OSError):
                    # Non-interactive fallback
                    update_choice = False

            if update_choice:
                print("[IMDb] Updating IMDb ratings dataset as requested...")
                should_download = True
            else:
                print(f"[WARNING] Continuing with the old IMDb dataset ({age_days} days old). Ratings may be outdated.\n")
                should_download = False
        else:
            print(f"[IMDb] Dataset is up-to-date ({age_days} days old, updated {last_updated_dt.strftime('%Y-%m-%d')}).")

    # Check if imdb_ratings table already has data
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(1) FROM imdb_ratings")
    existing_row_count = cursor.fetchone()[0]

    needs_load_to_db = should_download or (existing_row_count == 0)

    if should_download:
        download_imdb_gz(IMDB_GZ_PATH)
        gunzip_file(IMDB_GZ_PATH, IMDB_TSV_PATH)
    elif needs_load_to_db and not tsv_exists and gz_exists:
        gunzip_file(IMDB_GZ_PATH, IMDB_TSV_PATH)

    if needs_load_to_db:
        load_tsv_to_database(conn, IMDB_TSV_PATH)
        now_iso = datetime.now().isoformat()
        set_metadata(conn, "imdb_last_updated", now_iso)
        print(f"[OK] imdb_ratings table updated ({now_iso[:10]}).\n")

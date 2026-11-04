import os
import gzip
import csv
import json
import time
from datetime import datetime
from pathlib import Path
import requests

from config import IMDB_DATASET_URL, IMDB_DIR, IMDB_MAX_AGE_DAYS


IMDB_FILE_PATH = IMDB_DIR / "title.ratings.tsv.gz"
IMDB_META_PATH = IMDB_DIR / "metadata.json"


class IMDbRatingsManager:
    """Manages downloading, updating, and querying the official IMDb ratings dataset."""

    def __init__(self):
        self._cache = None  # in-memory dict: {tconst: (rating, votes)}

    def get_stored_download_date(self, conn=None):
        """Retrieve the last download date from the database or metadata file."""
        # 1. Try checking the database app_metadata table first
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM app_metadata WHERE key = 'imdb_dataset_downloaded_at'"
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return datetime.fromisoformat(row[0])
            except Exception:
                pass

        # 2. Try checking the metadata.json file
        if IMDB_META_PATH.exists():
            try:
                with open(IMDB_META_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "downloaded_at" in data:
                        return datetime.fromisoformat(data["downloaded_at"])
            except Exception:
                pass

        # 3. Fallback to file modification time
        if IMDB_FILE_PATH.exists():
            mtime = os.path.getmtime(IMDB_FILE_PATH)
            return datetime.fromtimestamp(mtime)

        return None

    def should_download(self, conn=None):
        """Check if the dataset file is missing or older than IMDB_MAX_AGE_DAYS."""
        if not IMDB_FILE_PATH.exists():
            return True

        download_date = self.get_stored_download_date(conn)
        if download_date is None:
            return True

        age_days = (datetime.now() - download_date).total_seconds() / 86400.0
        return age_days >= IMDB_MAX_AGE_DAYS

    def download_dataset(self, conn=None):
        """Download the IMDb ratings TSV gz file and record the download date."""
        IMDB_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = IMDB_DIR / "title.ratings.tsv.gz.tmp"

        print(f"Downloading IMDb dataset from {IMDB_DATASET_URL}...")
        t0 = time.time()

        response = requests.get(IMDB_DATASET_URL, stream=True, timeout=60)
        response.raise_for_status()

        total_bytes = int(response.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        percent = (downloaded / total_bytes) * 100
                        print(f"  Progress: {downloaded / 1024 / 1024:.1f} MB / {total_bytes / 1024 / 1024:.1f} MB ({percent:.0f}%)", end="\r")

        # Atomic replace
        if IMDB_FILE_PATH.exists():
            IMDB_FILE_PATH.unlink()
        temp_file.rename(IMDB_FILE_PATH)

        now = datetime.now()
        now_iso = now.isoformat()

        # Update metadata file
        with open(IMDB_META_PATH, "w", encoding="utf-8") as f:
            json.dump({"downloaded_at": now_iso, "url": IMDB_DATASET_URL}, f, indent=2)

        # Update database app_metadata table if conn provided
        if conn:
            try:
                conn.execute("""
                    INSERT INTO app_metadata (key, value) VALUES ('imdb_dataset_downloaded_at', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """, (now_iso,))
                conn.commit()
            except Exception as e:
                print(f"Warning: could not update DB metadata: {e}")

        elapsed = time.time() - t0
        print(f"\n[OK] IMDb ratings dataset downloaded in {elapsed:.1f}s (recorded date: {now.strftime('%Y-%m-%d %H:%M:%S')})")

        # Invalidate existing cache if any
        self._cache = None

    def ensure_dataset(self, conn=None):
        """Ensure dataset exists and is fresh; download if necessary."""
        last_date = self.get_stored_download_date(conn)
        if self.should_download(conn):
            if last_date:
                age_days = (datetime.now() - last_date).days
                print(f"IMDb dataset is {age_days} days old (exceeds limit of {IMDB_MAX_AGE_DAYS} days). Refreshing...")
            else:
                print("IMDb dataset not found locally. Downloading...")
            self.download_dataset(conn)
        else:
            age_days = (datetime.now() - last_date).days
            print(f"IMDb dataset is up-to-date ({age_days} days old, downloaded {last_date.strftime('%Y-%m-%d')}).")

    def load_cache(self):
        """Load ratings from gzipped TSV into an in-memory dictionary."""
        if self._cache is not None:
            return

        if not IMDB_FILE_PATH.exists():
            raise FileNotFoundError(f"IMDb dataset file not found at {IMDB_FILE_PATH}")

        print("Loading IMDb ratings into memory...", end=" ", flush=True)
        t0 = time.time()
        cache = {}

        with gzip.open(IMDB_FILE_PATH, "rt", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            # Skip header: tconst, averageRating, numVotes
            header = next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    try:
                        # tconst -> (averageRating, numVotes)
                        cache[row[0]] = (float(row[1]), int(row[2]))
                    except (ValueError, IndexError):
                        continue

        self._cache = cache
        print(f"done ({len(cache):,} titles loaded in {time.time() - t0:.2f}s)")

    def get_rating(self, imdb_id, conn=None):
        """Retrieve IMDb rating and vote count for an IMDb ID.

        Returns
        -------
        dict or None:
            {"imdb_rating": float, "imdb_votes": int}
        """
        if not imdb_id:
            return None

        # Clean ID
        imdb_id = imdb_id.strip()

        if self._cache is None:
            self.ensure_dataset(conn)
            self.load_cache()

        data = self._cache.get(imdb_id)
        if data:
            return {
                "imdb_rating": data[0],
                "imdb_votes": data[1]
            }
        return None


# Global manager instance
imdb_manager = IMDbRatingsManager()


def get_imdb_rating(imdb_id, conn=None):
    """Drop-in replacement for the old omdb get_imdb_rating function."""
    return imdb_manager.get_rating(imdb_id, conn=conn)

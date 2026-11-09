import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# TMDb API configuration
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Project paths
PROJECT_DIR = Path(__file__).parents[1].resolve()
DB_PATH = PROJECT_DIR / "database" / "letterboxd.db"
EXPORTS_DIR = PROJECT_DIR / "data_exports"

# IMDb dataset paths & settings
IMDB_DIR = PROJECT_DIR / "imdb_dataset"
IMDB_DATASET_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
IMDB_GZ_PATH = IMDB_DIR / "title.ratings.tsv.gz"
IMDB_TSV_PATH = IMDB_DIR / "title.ratings.tsv"
IMDB_MAX_AGE_DAYS = 30

# Schema version
SCHEMA_VERSION = "1.1.0"

# Cast selection rule: max(min(30% of total cast, 25), 10)
CAST_FRACTION = 0.30
CAST_MAX = 25
CAST_MIN = 10
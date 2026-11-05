import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# TMDb API configuration
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Project paths
PROJECT_DIR = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "letterboxd.db"
EXPORTS_DIR = DATA_DIR / "exports"

# IMDb dataset paths & settings
IMDB_DIR = DATA_DIR / "imdb"
IMDB_DATASET_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
IMDB_GZ_PATH = IMDB_DIR / "title.ratings.tsv.gz"
IMDB_TSV_PATH = IMDB_DIR / "title.ratings.tsv"
IMDB_MAX_AGE_DAYS = 30

# Schema version
SCHEMA_VERSION = "1.0.0"

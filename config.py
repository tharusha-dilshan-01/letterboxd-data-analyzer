import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API credentials
TMDB_TOKEN = os.getenv("TMDB_TOKEN")

# TMDb configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Project paths
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "letterboxd.db"
EXPORTS_DIR = DATA_DIR / "exports"

# IMDb dataset configuration
IMDB_DATASET_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
IMDB_DIR = DATA_DIR / "imdb"
IMDB_MAX_AGE_DAYS = 30

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API credentials
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

# TMDb configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Project paths
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "letterboxd.db"
EXPORTS_DIR = DATA_DIR / "exports"

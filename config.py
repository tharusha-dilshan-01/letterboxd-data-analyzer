import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API credentials
TMDB_TOKEN = os.getenv("TMDB_TOKEN")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

# TMDb configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"

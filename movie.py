from dataclasses import dataclass


@dataclass
class Movie:
    movie_id: int = None
    uri: str = ""
    name: str = ""
    year: int = 0
    rating: float = None
    rated_date: str = ""
    tmdb_id: int = None
    imdb_id: str = None
    runtime: int = None
    original_language: str = None
    poster_path: str = None
    backdrop_path: str = None
    collection_id: int = None
    fetch_status: str = "pending"
    is_active: int = 1

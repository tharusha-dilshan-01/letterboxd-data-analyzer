from dataclasses import dataclass, field


@dataclass
class Movie:
    # Information from Letterboxd
    name: str
    year: int
    letterboxd_uri: str = ""
    rating_date: str = ""
    user_rating: float = None

    # Information from TMDb
    tmdb_id: int = None
    imdb_id: str = None
    genres: list = field(default_factory=list)
    countries: list = field(default_factory=list)
    languages: list = field(default_factory=list)
    runtime: int = None
    directors: list = field(default_factory=list)
    cast: list = field(default_factory=list)
    tmdb_rating: float = None
    tmdb_votes: int = None

    # Information from IMDb
    imdb_rating: float = None
    imdb_votes: int = None

    def update_metadata(self, tmdb_data, imdb_data=None):
        """Update movie attributes using TMDb and IMDb data."""

        self.tmdb_id = tmdb_data["id"]
        self.imdb_id = tmdb_data.get("imdb_id")

        self.genres = [
            genre["name"]
            for genre in tmdb_data["genres"]
        ]

        self.countries = [
            country["name"]
            for country in tmdb_data["production_countries"]
        ]

        self.languages = [
            language["english_name"]
            for language in tmdb_data["spoken_languages"]
        ]

        self.runtime = tmdb_data.get("runtime")
        self.tmdb_rating = tmdb_data.get("vote_average")
        self.tmdb_votes = tmdb_data.get("vote_count")

        self.directors = [
            person["name"]
            for person in tmdb_data["credits"]["crew"]
            if person["job"] == "Director"
        ]

        cast_data = tmdb_data["credits"]["cast"]

        MAX_CAST = 25
        n = min(len(cast_data), MAX_CAST)

        self.cast = [
            person["name"]
            for person in cast_data[:n]
        ]

        if imdb_data:
            self.imdb_rating = imdb_data.get("imdb_rating")
            self.imdb_votes = imdb_data.get("imdb_votes")

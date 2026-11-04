from dataclasses import dataclass, field


@dataclass
class Movie:
    # Movie title and year
    name: str
    year: int

    # TMDb metadata
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

    # IMDb metadata
    imdb_rating: float = None
    imdb_votes: int = None

    # Optional Letterboxd context
    letterboxd_uri: str = ""
    rating_date: str = ""
    user_rating: float = None

    def update_metadata(self, tmdb_data, imdb_data=None):
        """Update movie attributes using TMDb details payload and IMDb dataset lookup."""
        self.tmdb_id = tmdb_data["id"]
        self.imdb_id = tmdb_data.get("imdb_id")

        self.genres = [
            genre["name"]
            for genre in tmdb_data.get("genres", [])
        ]

        self.countries = [
            country["name"]
            for country in tmdb_data.get("production_countries", [])
        ]

        self.languages = [
            language.get("english_name") or language.get("name")
            for language in tmdb_data.get("spoken_languages", [])
        ]

        self.runtime = tmdb_data.get("runtime")
        self.tmdb_rating = tmdb_data.get("vote_average")
        self.tmdb_votes = tmdb_data.get("vote_count")

        credits = tmdb_data.get("credits", {})
        crew = credits.get("crew", [])
        self.directors = [
            person["name"]
            for person in crew
            if person.get("job") == "Director"
        ]

        cast_data = credits.get("cast", [])
        MAX_CAST = 25
        n = min(len(cast_data), MAX_CAST)
        self.cast = [
            person["name"]
            for person in cast_data[:n]
        ]

        if imdb_data:
            self.imdb_rating = imdb_data.get("imdb_rating")
            self.imdb_votes = imdb_data.get("imdb_votes")

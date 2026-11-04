from tmdb import search_movie, get_movie_details
from omdb import get_imdb_rating
from movie import Movie

# Initial Letterboxd export data (currently hardcoded)
movie_name = "John Wick"
movie_year = 2014
watched_date = "2026-10-31" # Placeholder for Letterboxd diary date
user_rating = 4.5           # Placeholder for Letterboxd rating

# Search for the movie
movie_id = search_movie(movie_name, movie_year)

if movie_id is None:
    print(f"Movie '{movie_name}' not found!")

else:
    # 1. Initialize the Movie dataclass with base Letterboxd data
    current_movie = Movie(
        name=movie_name,
        year=movie_year,
        watched_date=watched_date,
        user_rating=user_rating
    )

    # 2. Retrieve TMDb and IMDb data
    tmdb_data = get_movie_details(movie_id)
    imdb_id = tmdb_data.get("imdb_id")
    imdb_data = get_imdb_rating(imdb_id) if imdb_id else None

    # 3. Populate the dataclass using your custom method
    current_movie.update_metadata(tmdb_data, imdb_data)

    # 4. Display movie information
    print("\n========== MOVIE DETAILS ==========")
    print(f"Title: {current_movie.name} ({current_movie.year})")
    print(f"Watched On: {current_movie.watched_date} | Your Rating: {current_movie.user_rating}/5.0")
    
    print("\nGenres:", ", ".join(current_movie.genres))
    print("Countries:", ", ".join(current_movie.countries))
    print("Spoken languages:", ", ".join(current_movie.languages))
    print("Runtime:", f"{current_movie.runtime} minutes")
    
    print("Director(s):", ", ".join(current_movie.directors))
    print("Cast:", ", ".join(current_movie.cast))

    print("\n--- RATINGS ---")
    print(f"TMDb rating: {current_movie.tmdb_rating} ({current_movie.tmdb_votes} votes)")
    
    if current_movie.imdb_rating:
        print(f"IMDb rating: {current_movie.imdb_rating} ({current_movie.imdb_votes} votes)")
    else:
        print("IMDb rating: Unavailable")
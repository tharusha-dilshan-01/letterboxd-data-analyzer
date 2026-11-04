import requests

from config import TMDB_TOKEN, TMDB_BASE_URL


# Headers used for TMDb API requests
headers = {
    "Authorization": f"Bearer {TMDB_TOKEN}",
    "accept": "application/json"
}


def search_movie(movie_name, movie_year=None):
    """Search for a movie and return its TMDb ID."""

    url = f"{TMDB_BASE_URL}/search/movie"

    params = {
        "query": movie_name
    }

    if movie_year:
        params["year"] = movie_year

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    results = response.json()["results"]

    if not results:
        return None

    # Find an exact title and year match
    movie = next(
        (
            item for item in results
            if item["title"].lower() == movie_name.lower()
            and (
                not movie_year
                or item.get("release_date", "").startswith(str(movie_year))
            )
        ),
        results[0]
    )

    return movie["id"]


def get_movie_details(movie_id):
    """Retrieve detailed information about a movie."""

    url = f"{TMDB_BASE_URL}/movie/{movie_id}"

    params = {
        "append_to_response": "credits"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    return response.json()

import requests

from config import OMDB_API_KEY


def get_imdb_rating(imdb_id):
    """Retrieve IMDb rating and vote count using an IMDb ID."""

    url = "https://www.omdbapi.com/"

    params = {
        "apikey": OMDB_API_KEY,
        "i": imdb_id,
        "r": "json"
    }

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    result = response.json()

    if result.get("Response") == "False":
        print("OMDb error:", result.get("Error"))
        return None

    # Extract IMDb rating
    rating = result.get("imdbRating")

    if rating == "N/A":
        rating = None
    else:
        rating = float(rating)

    # Extract IMDb vote count
    votes = result.get("imdbVotes")

    if votes == "N/A":
        votes = None
    else:
        votes = int(votes.replace(",", ""))

    return {
        "imdb_rating": rating,
        "imdb_votes": votes
    }

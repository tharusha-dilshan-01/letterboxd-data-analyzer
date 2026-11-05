import requests
from config import TMDB_TOKEN, TMDB_BASE_URL

# Standard headers for TMDb v3 API
headers = {
    "Authorization": f"Bearer {TMDB_TOKEN}",
    "accept": "application/json",
}


def _fetch_search(query: str, year=None):
    """Execute a single TMDb search request."""
    url = f"{TMDB_BASE_URL}/search/movie"
    params = {"query": query}
    if year is not None:
        params["year"] = int(year)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        print(f"  [TMDb Error] Search error for '{query}' ({year}): {e}")
        return []


def _pick_best_match(results, target_name: str):
    """Select the best match from search results:
    1. Exact title match (case-insensitive title or original_title)
    2. Highest popularity
    """
    if not results:
        return None

    clean_target = target_name.strip().lower()

    # Filter for exact title match
    exact_matches = [
        item for item in results
        if item.get("title", "").strip().lower() == clean_target
        or item.get("original_title", "").strip().lower() == clean_target
    ]

    candidates = exact_matches if exact_matches else results

    # Sort candidates by popularity descending
    sorted_candidates = sorted(
        candidates,
        key=lambda x: float(x.get("popularity") or 0.0),
        reverse=True
    )
    return sorted_candidates[0]["id"]


def search_movie(movie_name: str, movie_year: int = None):
    """Search TMDb by name and year.
    If no match, retries with year ± 1.
    Prefers exact title match, then popularity.
    """
    if not movie_name:
        return None

    # 1. Primary search with given year
    if movie_year:
        results = _fetch_search(movie_name, movie_year)
        if results:
            match_id = _pick_best_match(results, movie_name)
            if match_id:
                return match_id

        # 2. Retry with year - 1
        results_minus = _fetch_search(movie_name, movie_year - 1)
        if results_minus:
            match_id = _pick_best_match(results_minus, movie_name)
            if match_id:
                return match_id

        # 3. Retry with year + 1
        results_plus = _fetch_search(movie_name, movie_year + 1)
        if results_plus:
            match_id = _pick_best_match(results_plus, movie_name)
            if match_id:
                return match_id

    # 4. Fallback search without year restriction
    results_open = _fetch_search(movie_name, None)
    if results_open:
        return _pick_best_match(results_open, movie_name)

    return None


def get_movie_details(movie_id: int):
    """Retrieve detailed information about a movie with credits appended."""
    url = f"{TMDB_BASE_URL}/movie/{movie_id}"
    params = {"append_to_response": "credits"}

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def get_collection_details(collection_id: int):
    """Retrieve information about a collection and its parts."""
    url = f"{TMDB_BASE_URL}/collection/{collection_id}"

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()

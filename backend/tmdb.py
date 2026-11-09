import requests
from core.config import TMDB_TOKEN, TMDB_BASE_URL

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


def _pick_best_match(results, target_name: str, target_year: int | None = None):
    """Select the best match from search results:
    1. Exact title match (title or original_title) AND exact release year (if given)
    2. Exact title match with release year within ±1
    3. Exact title match with any release year
    4. Fall back to best popularity with release year proximity
    """
    if not results:
        return None

    clean_target = target_name.strip().lower()

    # Filter for exact title match (title or original_title)
    title_matches = [
        item for item in results
        if item.get("title", "").strip().lower() == clean_target
        or item.get("original_title", "").strip().lower() == clean_target
    ]

    candidates = title_matches if title_matches else results

    def score(item):
        release_date = item.get("release_date") or ""
        item_year = None
        if len(release_date) >= 4 and release_date[:4].isdigit():
            item_year = int(release_date[:4])

        # Exact year match gets highest bonus, ±1 gets secondary bonus
        year_score = 0
        if target_year is not None and item_year is not None:
            if item_year == target_year:
                year_score = 2
            elif abs(item_year - target_year) <= 1:
                year_score = 1
        elif target_year is None:
            year_score = 1

        popularity = float(item.get("popularity") or 0.0)
        return (year_score, popularity)

    sorted_candidates = sorted(candidates, key=score, reverse=True)
    return sorted_candidates[0]["id"]


def search_movie(movie_name: str, movie_year: int = None):
    """Search TMDb by name and year.
    If no match, retries with year ± 1.
    Prefers exact title match, then exact year, then popularity.
    """
    if not movie_name:
        return None

    # 1. Primary search with given year
    if movie_year:
        results = _fetch_search(movie_name, movie_year)
        if results:
            match_id = _pick_best_match(results, movie_name, movie_year)
            if match_id:
                return match_id

        # 2. Retry with year - 1
        results_minus = _fetch_search(movie_name, movie_year - 1)
        if results_minus:
            match_id = _pick_best_match(results_minus, movie_name, movie_year - 1)
            if match_id:
                return match_id

        # 3. Retry with year + 1
        results_plus = _fetch_search(movie_name, movie_year + 1)
        if results_plus:
            match_id = _pick_best_match(results_plus, movie_name, movie_year + 1)
            if match_id:
                return match_id

    # 4. Fallback search without year restriction
    results_open = _fetch_search(movie_name, None)
    if results_open:
        return _pick_best_match(results_open, movie_name, movie_year)

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

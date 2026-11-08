import math
from datetime import datetime

from config import CAST_FRACTION, CAST_MAX, CAST_MIN
from tmdb import search_movie, get_movie_details, get_collection_details


def save_collection(cursor, collection_id, collection_info, movie_year, release_date):
    """Fetch and upsert collection details before the movie row references it."""
    if not collection_id:
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT fetched_at FROM collections WHERE collection_id = ?", (collection_id,))
    coll_row = cursor.fetchone()

    movie_release = release_date or str(movie_year)
    needs_fetch = False

    if not coll_row:
        needs_fetch = True
    else:
        fetched_at = coll_row[0] or ""
        if fetched_at[:10] < movie_release[:10]:
            needs_fetch = True

    if not needs_fetch:
        return

    try:
        coll_data = get_collection_details(collection_id)
        coll_name = coll_data.get("name") or collection_info.get("name") or "Collection"
        coll_poster = coll_data.get("poster_path")
        coll_backdrop = coll_data.get("backdrop_path")
        parts = coll_data.get("parts") or []

        # Count released parts only
        released_parts = [
            p for p in parts
            if p.get("release_date") and p.get("release_date").strip() <= today_str
        ]
        total_movies = len(released_parts)
        coll_fetched_at = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO collections (
                collection_id, collection_name, total_movies,
                poster_path, backdrop_path, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(collection_id) DO UPDATE SET
                collection_name = excluded.collection_name,
                total_movies = excluded.total_movies,
                poster_path = excluded.poster_path,
                backdrop_path = excluded.backdrop_path,
                fetched_at = excluded.fetched_at;
        """, (collection_id, coll_name, total_movies, coll_poster, coll_backdrop, coll_fetched_at))
    except Exception as ce:
        print(f" [Collection note: {ce}]", end="", flush=True)


def save_people_and_cast(cursor, movie_id, raw_cast):
    """Save selected cast members into people (with gender) and movie_cast link table.
    Cast selection formula: max(min(ceil(total * 30%), 25), 10).
    """
    total_cast = len(raw_cast)
    num_selected = max(min(math.ceil(total_cast * CAST_FRACTION), CAST_MAX), CAST_MIN)
    selected_cast = raw_cast[:num_selected]

    # 1. Upsert into people table
    for p in selected_cast:
        p_id = p.get("id")
        p_name = p.get("name")
        profile = p.get("profile_path")
        gender = p.get("gender") or 0
        if p_id and p_name:
            cursor.execute("""
                INSERT INTO people (person_id, name, profile_paths, gender)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    name = excluded.name,
                    profile_paths = COALESCE(excluded.profile_paths, people.profile_paths),
                    gender = CASE WHEN excluded.gender != 0 THEN excluded.gender ELSE people.gender END;
            """, (p_id, p_name, profile, gender))

    # 2. Upsert into movie_cast link table
    cursor.execute("DELETE FROM movie_cast WHERE movie_id = ?", (movie_id,))
    for idx, member in enumerate(selected_cast):
        p_id = member.get("id")
        order = member.get("order", idx)
        if p_id:
            cursor.execute("""
                INSERT OR REPLACE INTO movie_cast (movie_id, person_id, billing_order)
                VALUES (?, ?, ?);
            """, (movie_id, p_id, order))


def save_directors(cursor, movie_id, crew):
    """Extract and save directors into people table and movie_directors link table."""
    directors = [c for c in crew if c.get("job") == "Director"]

    # 1. Upsert directors into people table
    for d in directors:
        p_id = d.get("id")
        p_name = d.get("name")
        profile = d.get("profile_path")
        gender = d.get("gender") or 0
        if p_id and p_name:
            cursor.execute("""
                INSERT INTO people (person_id, name, profile_paths, gender)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    name = excluded.name,
                    profile_paths = COALESCE(excluded.profile_paths, people.profile_paths),
                    gender = CASE WHEN excluded.gender != 0 THEN excluded.gender ELSE people.gender END;
            """, (p_id, p_name, profile, gender))

    # 2. Upsert into movie_directors link table
    cursor.execute("DELETE FROM movie_directors WHERE movie_id = ?", (movie_id,))
    for d in directors:
        p_id = d.get("id")
        if p_id:
            cursor.execute("""
                INSERT OR REPLACE INTO movie_directors (movie_id, person_id)
                VALUES (?, ?);
            """, (movie_id, p_id))


def save_genres(cursor, movie_id, genres):
    """Save film genres into movie_genres link table."""
    cursor.execute("DELETE FROM movie_genres WHERE movie_id = ?", (movie_id,))
    for g in genres:
        g_id = g.get("id")
        g_name = g.get("name")
        if g_id and g_name:
            cursor.execute("""
                INSERT OR REPLACE INTO movie_genres (movie_id, genre_id, genre_name)
                VALUES (?, ?, ?);
            """, (movie_id, g_id, g_name))


def save_production_countries(cursor, movie_id, production_countries):
    """Save production countries into countries table and movie_countries link table."""
    cursor.execute("DELETE FROM movie_countries WHERE movie_id = ?", (movie_id,))
    for country in production_countries:
        code = country.get("iso_3166_1")
        name = country.get("name")
        if code and name:
            clean_code = str(code).strip().upper()
            cursor.execute("""
                INSERT INTO countries (country_code, name)
                VALUES (?, ?)
                ON CONFLICT(country_code) DO UPDATE SET name = excluded.name;
            """, (clean_code, name.strip()))
            cursor.execute("""
                INSERT OR REPLACE INTO movie_countries (movie_id, country_code)
                VALUES (?, ?);
            """, (movie_id, clean_code))


def save_production_companies(cursor, movie_id, production_companies):
    """Save production companies into companies table and movie_companies link table."""
    cursor.execute("DELETE FROM movie_companies WHERE movie_id = ?", (movie_id,))
    for company in production_companies:
        c_id = company.get("id")
        c_name = company.get("name")
        if c_id and c_name:
            cursor.execute("""
                INSERT INTO companies (company_id, name, logo_path, origin_country)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (company_id) DO UPDATE SET
                    name = excluded.name,
                    logo_path = COALESCE(excluded.logo_path, companies.logo_path),
                    origin_country = COALESCE(NULLIF(excluded.origin_country, ''), companies.origin_country);
            """, (c_id, c_name.strip(), company.get("logo_path"), company.get("origin_country")))
            cursor.execute("""
                INSERT OR REPLACE INTO movie_companies (movie_id, company_id)
                VALUES (?, ?);
            """, (movie_id, c_id))


def enrich_movie(conn, movie_id, name, year, existing_tmdb_id=None):
    """Enrich a single movie record with full TMDb metadata.
    Returns: 'ok', 'not_found', or 'failed'.
    """
    cursor = conn.cursor()

    # 1. Resolve TMDb ID: reuse existing if valid, otherwise search TMDb
    tmdb_id = existing_tmdb_id
    if not tmdb_id:
        tmdb_id = search_movie(name, year)

    if not tmdb_id:
        cursor.execute("UPDATE movies SET fetch_status = 'not_found' WHERE movie_id = ?", (movie_id,))
        conn.commit()
        return "not_found"

    # 2. Fetch detailed metadata with credits
    details = get_movie_details(tmdb_id)

    imdb_id = details.get("imdb_id")
    runtime = details.get("runtime")
    original_language = details.get("original_language")
    poster_path = details.get("poster_path")
    backdrop_path = details.get("backdrop_path")
    release_date = details.get("release_date") or ""
    production_countries = details.get("production_countries") or []
    production_companies = details.get("production_companies") or []
    genres = details.get("genres") or []

    # 3. Collection handling
    collection_info = details.get("belongs_to_collection")
    collection_id = collection_info.get("id") if collection_info else None
    if collection_id:
        save_collection(cursor, collection_id, collection_info, year, release_date)

    # 4. Save link tables & entities
    credits = details.get("credits") or {}
    raw_cast = credits.get("cast") or []
    crew = credits.get("crew") or []

    save_people_and_cast(cursor, movie_id, raw_cast)
    save_directors(cursor, movie_id, crew)
    save_genres(cursor, movie_id, genres)
    save_production_countries(cursor, movie_id, production_countries)
    save_production_companies(cursor, movie_id, production_companies)

    # 5. Update movies row
    cursor.execute("""
        UPDATE movies SET
            tmdb_id = ?,
            imdb_id = ?,
            runtime = ?,
            original_language = ?,
            poster_path = ?,
            backdrop_path = ?,
            collection_id = ?,
            fetch_status = 'ok'
        WHERE movie_id = ?;
    """, (tmdb_id, imdb_id, runtime, original_language, poster_path, backdrop_path, collection_id, movie_id))

    conn.commit()
    return "ok"

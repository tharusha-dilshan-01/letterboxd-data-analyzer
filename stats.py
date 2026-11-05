"""Statistics calculation module.
All queries read strictly from the `active_movies` view as required by Step 5.
Uses `localization.py` (Step 4) to convert country and language codes.
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from database import get_connection
from localization import get_country_name, get_language_name


def get_rating_distribution(conn):
    """Vertical bar distribution of total movies per rating (scaled to 1-10)."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            CAST(ROUND(rating * 2) AS INTEGER) AS rating_10,
            COUNT(*) AS count
        FROM active_movies
        WHERE rating IS NOT NULL
        GROUP BY rating_10
        ORDER BY rating_10 ASC;
    """)
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_release_year_distribution(conn, group_by="year"):
    """Release year distribution with a 'year' or 'decade' toggle."""
    cursor = conn.cursor()
    if group_by == "decade":
        cursor.execute("""
            SELECT (year / 10) * 10 AS decade, COUNT(*) AS count
            FROM active_movies
            GROUP BY decade
            ORDER BY decade ASC;
        """)
    else:
        cursor.execute("""
            SELECT year, COUNT(*) AS count
            FROM active_movies
            GROUP BY year
            ORDER BY year ASC;
        """)
    return cursor.fetchall()


def get_top_genres(conn, mode="most_watched"):
    """Top genres with toggle: 'most_watched' (count) or 'highest_average' (average user rating).
    For highest average: requires at least min(10, 5% of total movies).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_movies;")
    total_movies = cursor.fetchone()[0] or 1
    min_threshold = min(10, max(1, int(0.05 * total_movies)))

    if mode == "highest_average":
        cursor.execute("""
            SELECT mg.genre_name,
                   ROUND(AVG(m.rating * 2), 2) AS avg_rating,
                   COUNT(m.movie_id) AS movie_count
            FROM active_movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            WHERE m.rating IS NOT NULL
            GROUP BY mg.genre_name
            HAVING movie_count >= ?
            ORDER BY avg_rating DESC, movie_count DESC
            LIMIT 15;
        """, (min_threshold,))
    else:
        cursor.execute("""
            SELECT mg.genre_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2), 2) AS avg_rating
            FROM active_movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            GROUP BY mg.genre_name
            ORDER BY movie_count DESC
            LIMIT 15;
        """)
    return cursor.fetchall()


def get_top_countries(conn, mode="most_watched"):
    """Top countries with names resolved via pycountry."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_movies;")
    total_movies = cursor.fetchone()[0] or 1
    min_threshold = min(10, max(1, int(0.05 * total_movies)))

    if mode == "highest_average":
        cursor.execute("""
            SELECT mc.country_code,
                   ROUND(AVG(m.rating * 2), 2) AS avg_rating,
                   COUNT(m.movie_id) AS movie_count
            FROM active_movies m
            JOIN movie_countries mc ON m.movie_id = mc.movie_id
            WHERE m.rating IS NOT NULL
            GROUP BY mc.country_code
            HAVING movie_count >= ?
            ORDER BY avg_rating DESC, movie_count DESC
            LIMIT 15;
        """, (min_threshold,))
    else:
        cursor.execute("""
            SELECT mc.country_code,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2), 2) AS avg_rating
            FROM active_movies m
            JOIN movie_countries mc ON m.movie_id = mc.movie_id
            GROUP BY mc.country_code
            ORDER BY movie_count DESC
            LIMIT 15;
        """)

    results = []
    for code, count_or_avg, other in cursor.fetchall():
        name = get_country_name(code)
        results.append((name, count_or_avg, other))
    return results


def get_top_languages(conn, mode="most_watched"):
    """Top languages with names resolved via pycountry."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_movies;")
    total_movies = cursor.fetchone()[0] or 1
    min_threshold = min(10, max(1, int(0.05 * total_movies)))

    if mode == "highest_average":
        cursor.execute("""
            SELECT original_language,
                   ROUND(AVG(rating * 2), 2) AS avg_rating,
                   COUNT(movie_id) AS movie_count
            FROM active_movies
            WHERE rating IS NOT NULL AND original_language IS NOT NULL
            GROUP BY original_language
            HAVING movie_count >= ?
            ORDER BY avg_rating DESC, movie_count DESC
            LIMIT 15;
        """, (min_threshold,))
    else:
        cursor.execute("""
            SELECT original_language,
                   COUNT(movie_id) AS movie_count,
                   ROUND(AVG(rating * 2), 2) AS avg_rating
            FROM active_movies
            WHERE original_language IS NOT NULL
            GROUP BY original_language
            ORDER BY movie_count DESC
            LIMIT 15;
        """)

    results = []
    for code, val1, val2 in cursor.fetchall():
        name = get_language_name(code)
        results.append((name, val1, val2))
    return results


def get_top_directors(conn, limit=10):
    """Most watched directors."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, COUNT(m.movie_id) AS watch_count, ROUND(AVG(m.rating * 2), 2) AS avg_rating
        FROM active_movies m
        JOIN movie_directors md ON m.movie_id = md.movie_id
        JOIN people p ON md.person_id = p.person_id
        GROUP BY p.person_id, p.name
        ORDER BY watch_count DESC, avg_rating DESC
        LIMIT ?;
    """, (limit,))
    return cursor.fetchall()


def get_top_actors(conn, limit=10):
    """Most watched actors."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, COUNT(m.movie_id) AS watch_count, ROUND(AVG(m.rating * 2), 2) AS avg_rating
        FROM active_movies m
        JOIN movie_cast mc ON m.movie_id = mc.movie_id
        JOIN people p ON mc.person_id = p.person_id
        GROUP BY p.person_id, p.name
        ORDER BY watch_count DESC, avg_rating DESC
        LIMIT ?;
    """, (limit,))
    return cursor.fetchall()


def get_imdb_rating_differences(conn, limit=10):
    """Top 10 largest rating differences vs IMDb (positive and negative).
    Only films with IMDb votes >= 1,000.
    Letterboxd rating is scaled to 10 for comparison with IMDb rating (1-10).
    Returns (positive_diffs, negative_diffs).
    """
    cursor = conn.cursor()
    # Positive diff: user liked it much more than IMDb average
    cursor.execute("""
        SELECT m.name, m.year,
               (m.rating * 2.0) AS user_10,
               i.rating AS imdb_10,
               ROUND((m.rating * 2.0) - i.rating, 2) AS diff,
               i.votes
        FROM active_movies m
        JOIN imdb_ratings i ON m.imdb_id = i.imdb_id
        WHERE m.rating IS NOT NULL
          AND i.votes >= 1000
        ORDER BY diff DESC
        LIMIT ?;
    """, (limit,))
    positive = cursor.fetchall()

    # Negative diff: user liked it much less than IMDb average
    cursor.execute("""
        SELECT m.name, m.year,
               (m.rating * 2.0) AS user_10,
               i.rating AS imdb_10,
               ROUND((m.rating * 2.0) - i.rating, 2) AS diff,
               i.votes
        FROM active_movies m
        JOIN imdb_ratings i ON m.imdb_id = i.imdb_id
        WHERE m.rating IS NOT NULL
          AND i.votes >= 1000
        ORDER BY diff ASC
        LIMIT ?;
    """, (limit,))
    negative = cursor.fetchall()

    return positive, negative


def get_collection_stats(conn):
    """Collection stats: watched X of Y per collection using total_movies."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.collection_name,
               COUNT(m.movie_id) AS watched_count,
               c.total_movies,
               ROUND((COUNT(m.movie_id) * 100.0) / MAX(c.total_movies, 1), 1) AS percent_completed
        FROM active_movies m
        JOIN collections c ON m.collection_id = c.collection_id
        GROUP BY c.collection_id, c.collection_name, c.total_movies
        ORDER BY percent_completed DESC, watched_count DESC;
    """)
    return cursor.fetchall()


def print_stats_summary():
    """Print a clean terminal dashboard of all statistics."""
    conn = get_connection()

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_movies;")
    total_active = cursor.fetchone()[0]

    print("\n" + "=" * 50)
    print(f"        LETTERBOXD STATS DASHBOARD ({total_active} Movies)")
    print("=" * 50)

    # 1. Rating Distribution
    print("\n[RATING DISTRIBUTION (Scale 1-10)]")
    dist = get_rating_distribution(conn)
    for r in range(1, 11):
        bar = "#" * dist.get(r, 0)
        print(f"  {r:2d}/10 | {bar} ({dist.get(r, 0)})")

    # 2. Top Genres
    print("\n[TOP GENRES - MOST WATCHED]")
    for g, count, avg in get_top_genres(conn, "most_watched")[:5]:
        print(f"  {g:<20} : {count:2d} movies (avg: {avg}/10)")

    # 3. Top Countries (Step 4 pycountry)
    print("\n[TOP COUNTRIES (pycountry resolved)]")
    for country, count, avg in get_top_countries(conn, "most_watched")[:5]:
        print(f"  {country:<20} : {count:2d} movies (avg: {avg}/10)")

    # 4. Top Languages (Step 4 pycountry)
    print("\n[TOP LANGUAGES (pycountry resolved)]")
    for lang, count, avg in get_top_languages(conn, "most_watched")[:5]:
        print(f"  {lang:<20} : {count:2d} movies (avg: {avg}/10)")

    # 5. Top Directors
    print("\n[TOP DIRECTORS]")
    for name, count, avg in get_top_directors(conn, 5):
        print(f"  {name:<25} : {count:2d} movies (avg: {avg}/10)")

    # 6. IMDb Differences
    pos, neg = get_imdb_rating_differences(conn, 3)
    print("\n[RATED HIGHER THAN IMDB (votes >= 1k)]")
    for name, yr, u_rat, i_rat, diff, votes in pos:
        print(f"  {name} ({yr}): You {u_rat}/10 vs IMDb {i_rat}/10 (+{diff})")

    print("\n[RATED LOWER THAN IMDB (votes >= 1k)]")
    for name, yr, u_rat, i_rat, diff, votes in neg:
        print(f"  {name} ({yr}): You {u_rat}/10 vs IMDb {i_rat}/10 ({diff})")

    # 7. Collection Stats
    print("\n[COLLECTION STATS]")
    for coll, watched, total, pct in get_collection_stats(conn)[:5]:
        print(f"  {coll}: watched {watched} of {total} ({pct}%)")

    print("=" * 50 + "\n")
    conn.close()

import sys
from pathlib import Path

# Add core directory to path so we can import config, database, localization
CORE_DIR = Path(__file__).resolve().parent.parent / "core"
ROOT_DIR = Path(__file__).resolve().parent.parent

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(1, str(ROOT_DIR))

import pandas as pd
from database import get_connection, get_metadata
from localization import get_country_name, get_language_name


def get_kpis():
    """Retrieve key summary metrics for the active movies."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) AS total_movies,
            ROUND(AVG(rating), 2) AS avg_rating,
            SUM(runtime) AS total_runtime_min,
            COUNT(DISTINCT collection_id) AS total_collections
        FROM active_movies;
    """)
    row = cursor.fetchone()

    cursor.execute("SELECT COUNT(DISTINCT person_id) FROM movie_directors WHERE movie_id IN (SELECT movie_id FROM active_movies);")
    unique_directors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT person_id) FROM movie_cast WHERE movie_id IN (SELECT movie_id FROM active_movies);")
    unique_actors = cursor.fetchone()[0]

    last_import = get_metadata(conn, "last_csv_import")
    last_imdb = get_metadata(conn, "imdb_last_updated")

    conn.close()

    total_min = row[2] or 0
    hours = total_min // 60
    days = round(hours / 24, 1)

    return {
        "total_movies": row[0] or 0,
        "avg_rating": row[1] or 0.0,
        "total_runtime_hours": hours,
        "total_runtime_days": days,
        "unique_directors": unique_directors,
        "unique_actors": unique_actors,
        "total_collections": row[3] or 0,
        "last_import": last_import[:16].replace("T", " ") if last_import else "Never",
        "last_imdb": last_imdb[:10] if last_imdb else "Unknown",
    }


def get_rating_distribution_df():
    """Rating distribution: counts for user ratings (1 to 10 scale)."""
    conn = get_connection()
    query = """
        SELECT
            CAST(ROUND(rating * 2) AS INTEGER) AS rating_scale_10,
            COUNT(*) AS movie_count
        FROM active_movies
        WHERE rating IS NOT NULL
        GROUP BY rating_scale_10
        ORDER BY rating_scale_10 ASC;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Ensure all ratings from 1 to 10 are represented
    full_scale = pd.DataFrame({"rating_scale_10": list(range(1, 11))})
    df = full_scale.merge(df, on="rating_scale_10", how="left").fillna(0)
    df["movie_count"] = df["movie_count"].astype(int)
    df["letterboxd_stars"] = (df["rating_scale_10"] / 2.0).astype(str) + " ★"
    return df


def get_release_year_df(group_by="year"):
    """Release year distribution with 'year' or 'decade' toggle."""
    conn = get_connection()
    if group_by == "decade":
        query = """
            SELECT (year / 10) * 10 AS period, COUNT(*) AS movie_count
            FROM active_movies
            GROUP BY period
            ORDER BY period ASC;
        """
    else:
        query = """
            SELECT year AS period, COUNT(*) AS movie_count
            FROM active_movies
            GROUP BY period
            ORDER BY period ASC;
        """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_category_stats_df(category="genres", mode="most_watched", limit=15):
    """Horizontal stats for genres, countries, years, languages.
    mode: 'most_watched' or 'highest_average'
    Applies minimum threshold: min(10, 5% of total movies).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM active_movies;")
    total_movies = cursor.fetchone()[0] or 1
    threshold = min(10, max(1, int(0.05 * total_movies)))

    if category == "genres":
        query = """
            SELECT mg.genre_name AS item_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2.0), 2) AS avg_rating
            FROM active_movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            WHERE m.rating IS NOT NULL
            GROUP BY mg.genre_name
        """
    elif category == "countries":
        query = """
            SELECT mc.country_code AS item_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2.0), 2) AS avg_rating
            FROM active_movies m
            JOIN movie_countries mc ON m.movie_id = mc.movie_id
            WHERE m.rating IS NOT NULL
            GROUP BY mc.country_code
        """
    elif category == "languages":
        query = """
            SELECT m.original_language AS item_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2.0), 2) AS avg_rating
            FROM active_movies m
            WHERE m.rating IS NOT NULL AND m.original_language IS NOT NULL
            GROUP BY m.original_language
        """
    elif category == "years":
        query = """
            SELECT CAST(m.year AS TEXT) AS item_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2.0), 2) AS avg_rating
            FROM active_movies m
            WHERE m.rating IS NOT NULL
            GROUP BY m.year
        """
    else:
        conn.close()
        return pd.DataFrame()

    if mode == "highest_average":
        query += f" HAVING movie_count >= {threshold} ORDER BY avg_rating DESC, movie_count DESC LIMIT {limit};"
    else:
        query += f" ORDER BY movie_count DESC, avg_rating DESC LIMIT {limit};"

    df = pd.read_sql_query(query, conn)
    conn.close()

    # Step 4 localization conversion
    if category == "countries" and not df.empty:
        df["item_name"] = df["item_name"].apply(get_country_name)
    elif category == "languages" and not df.empty:
        df["item_name"] = df["item_name"].apply(get_language_name)

    return df


def get_top_people_df(role="directors", limit=15):
    """Top watched directors or actors."""
    conn = get_connection()
    if role == "directors":
        query = f"""
            SELECT p.name AS person_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2.0), 2) AS avg_rating
            FROM active_movies m
            JOIN movie_directors md ON m.movie_id = md.movie_id
            JOIN people p ON md.person_id = p.person_id
            GROUP BY p.person_id, p.name
            ORDER BY movie_count DESC, avg_rating DESC
            LIMIT {limit};
        """
    else:
        query = f"""
            SELECT p.name AS person_name,
                   COUNT(m.movie_id) AS movie_count,
                   ROUND(AVG(m.rating * 2.0), 2) AS avg_rating
            FROM active_movies m
            JOIN movie_cast mc ON m.movie_id = mc.movie_id
            JOIN people p ON mc.person_id = p.person_id
            GROUP BY p.person_id, p.name
            ORDER BY movie_count DESC, avg_rating DESC
            LIMIT {limit};
        """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_imdb_differences_df(limit=10):
    """Top largest rating differences vs IMDb (positive and negative).
    Only films with IMDb votes >= 1,000.
    """
    conn = get_connection()
    base_query = """
        SELECT m.name AS title,
               m.year,
               ROUND(m.rating * 2.0, 1) AS your_rating,
               ROUND(i.rating, 1) AS imdb_rating,
               ROUND((m.rating * 2.0) - i.rating, 2) AS difference,
               i.votes AS imdb_votes
        FROM active_movies m
        JOIN imdb_ratings i ON m.imdb_id = i.imdb_id
        WHERE m.rating IS NOT NULL
          AND i.votes >= 1000
    """
    df_pos = pd.read_sql_query(base_query + f" ORDER BY difference DESC LIMIT {limit};", conn)
    df_neg = pd.read_sql_query(base_query + f" ORDER BY difference ASC LIMIT {limit};", conn)
    conn.close()
    return df_pos, df_neg


def get_collections_df():
    """Collection stats: watched X of Y per collection using total_movies."""
    conn = get_connection()
    query = """
        SELECT c.collection_name,
               COUNT(m.movie_id) AS watched_count,
               c.total_movies,
               ROUND((COUNT(m.movie_id) * 100.0) / MAX(c.total_movies, 1), 1) AS percent_completed,
               c.poster_path
        FROM active_movies m
        JOIN collections c ON m.collection_id = c.collection_id
        GROUP BY c.collection_id, c.collection_name, c.total_movies
        ORDER BY percent_completed DESC, watched_count DESC;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_all_movies_table():
    """Retrieve full movie list for searchable explorer table."""
    conn = get_connection()
    query = """
        SELECT m.name AS Title,
               m.year AS Year,
               m.rating AS Rating,
               ROUND(m.rating * 2.0, 1) AS "Rating (10)",
               m.rated_date AS "Watched On",
               i.rating AS "IMDb Rating",
               i.votes AS "IMDb Votes",
               m.runtime AS "Runtime (min)",
               m.original_language AS Lang,
               c.collection_name AS Collection,
               m.uri AS Letterboxd_URL,
               m.poster_path
        FROM active_movies m
        LEFT JOIN collections c ON m.collection_id = c.collection_id
        LEFT JOIN imdb_ratings i ON m.imdb_id = i.imdb_id
        ORDER BY m.rated_date DESC, m.name ASC;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if not df.empty and "Lang" in df.columns:
        df["Lang"] = df["Lang"].apply(get_language_name)
    return df

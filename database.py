import sqlite3
import json

from config import DB_PATH


def get_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables(conn):
    """Create all database tables and indexes if they don't already exist."""
    conn.executescript("""
        -- Table storing unique canonical movie metadata (TMDb ID is primary key)
        CREATE TABLE IF NOT EXISTS movies (
            tmdb_id         INTEGER PRIMARY KEY,
            name            TEXT    NOT NULL,
            year            INTEGER,
            imdb_id         TEXT,
            genres          TEXT,       -- JSON array
            countries       TEXT,       -- JSON array
            languages       TEXT,       -- JSON array
            runtime         INTEGER,
            directors       TEXT,       -- JSON array
            cast            TEXT,       -- JSON array
            tmdb_rating     REAL,
            tmdb_votes      INTEGER,
            imdb_rating     REAL,
            imdb_votes      INTEGER
        );

        -- Table storing user ratings from Letterboxd exports (tmdb_id is foreign key)
        CREATE TABLE IF NOT EXISTS ratings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            letterboxd_uri  TEXT    UNIQUE NOT NULL,
            tmdb_id         INTEGER NOT NULL,
            name            TEXT    NOT NULL,
            year            INTEGER NOT NULL,
            rating_date     TEXT,
            user_rating     REAL,
            FOREIGN KEY (tmdb_id) REFERENCES movies (tmdb_id) ON DELETE CASCADE
        );

        -- Key-value table for metadata (such as IMDb dataset download date)
        CREATE TABLE IF NOT EXISTS app_metadata (
            key             TEXT PRIMARY KEY,
            value           TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ratings_tmdb_id ON ratings(tmdb_id);
        CREATE INDEX IF NOT EXISTS idx_movies_name_year ON movies(name, year);
    """)
    conn.commit()


def movie_exists(conn, tmdb_id):
    """Check if a movie with given TMDb ID already exists in the movies table."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM movies WHERE tmdb_id = ? LIMIT 1", (tmdb_id,))
    return cursor.fetchone() is not None


def find_tmdb_id_by_uri(conn, letterboxd_uri):
    """Find TMDb ID if this Letterboxd URI was previously stored in ratings."""
    cursor = conn.cursor()
    cursor.execute("SELECT tmdb_id FROM ratings WHERE letterboxd_uri = ? LIMIT 1", (letterboxd_uri,))
    row = cursor.fetchone()
    return row[0] if row else None


def find_tmdb_id_by_title(conn, name, year):
    """Find TMDb ID if a movie with the exact name and year already exists in movies."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tmdb_id FROM movies WHERE LOWER(name) = LOWER(?) AND year = ? LIMIT 1",
        (name, year)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def save_movie(conn, movie):
    """Insert or update a movie in the movies table (keyed by tmdb_id).

    Parameters
    ----------
    conn : sqlite3.Connection
    movie : Movie dataclass instance
    """
    conn.execute("""
        INSERT INTO movies (
            tmdb_id, name, year, imdb_id, genres, countries,
            languages, runtime, directors, cast, tmdb_rating,
            tmdb_votes, imdb_rating, imdb_votes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tmdb_id) DO UPDATE SET
            name        = excluded.name,
            year        = excluded.year,
            imdb_id     = excluded.imdb_id,
            genres      = excluded.genres,
            countries   = excluded.countries,
            languages   = excluded.languages,
            runtime     = excluded.runtime,
            directors   = excluded.directors,
            cast        = excluded.cast,
            tmdb_rating = excluded.tmdb_rating,
            tmdb_votes  = excluded.tmdb_votes,
            imdb_rating = excluded.imdb_rating,
            imdb_votes  = excluded.imdb_votes
    """, (
        movie.tmdb_id,
        movie.name,
        movie.year,
        movie.imdb_id,
        json.dumps(movie.genres) if movie.genres else None,
        json.dumps(movie.countries) if movie.countries else None,
        json.dumps(movie.languages) if movie.languages else None,
        movie.runtime,
        json.dumps(movie.directors) if movie.directors else None,
        json.dumps(movie.cast) if movie.cast else None,
        movie.tmdb_rating,
        movie.tmdb_votes,
        movie.imdb_rating,
        movie.imdb_votes,
    ))
    conn.commit()


def save_rating(conn, letterboxd_uri, tmdb_id, name, year, rating_date, user_rating):
    """Insert or update a rating entry in the ratings table.

    Parameters
    ----------
    conn : sqlite3.Connection
    letterboxd_uri : str
    tmdb_id : int (Foreign key referencing movies.tmdb_id)
    name : str
    year : int
    rating_date : str
    user_rating : float
    """
    conn.execute("""
        INSERT INTO ratings (
            letterboxd_uri, tmdb_id, name, year, rating_date, user_rating
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(letterboxd_uri) DO UPDATE SET
            tmdb_id     = excluded.tmdb_id,
            name        = excluded.name,
            year        = excluded.year,
            rating_date = excluded.rating_date,
            user_rating = excluded.user_rating
    """, (
        letterboxd_uri,
        tmdb_id,
        name,
        year,
        rating_date,
        user_rating
    ))
    conn.commit()


def get_metadata(conn, key):
    """Retrieve a value from the app_metadata table."""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_metadata WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


def set_metadata(conn, key, value):
    """Store or update a key-value pair in the app_metadata table."""
    conn.execute("""
        INSERT INTO app_metadata (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()

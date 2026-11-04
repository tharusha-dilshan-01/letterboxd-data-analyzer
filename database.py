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
    """Create all database tables if they don't already exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS movies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            year            INTEGER NOT NULL,
            letterboxd_uri  TEXT    UNIQUE NOT NULL,
            rating_date     TEXT,
            user_rating     REAL,

            -- TMDb metadata
            tmdb_id         INTEGER,
            imdb_id         TEXT,
            genres          TEXT,       -- JSON array
            countries       TEXT,       -- JSON array
            languages       TEXT,       -- JSON array
            runtime         INTEGER,
            directors       TEXT,       -- JSON array
            cast            TEXT,       -- JSON array
            tmdb_rating     REAL,
            tmdb_votes      INTEGER,

            -- IMDb metadata
            imdb_rating     REAL,
            imdb_votes      INTEGER,

            UNIQUE(name, year)
        );
    """)
    conn.commit()


def upsert_movie(conn, movie):
    """Insert or update a movie record.

    Parameters
    ----------
    conn : sqlite3.Connection
    movie : Movie dataclass instance
    """
    conn.execute("""
        INSERT INTO movies (
            name, year, letterboxd_uri, rating_date, user_rating,
            tmdb_id, imdb_id, genres, countries, languages,
            runtime, directors, cast, tmdb_rating, tmdb_votes,
            imdb_rating, imdb_votes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name, year) DO UPDATE SET
            letterboxd_uri = excluded.letterboxd_uri,
            rating_date    = excluded.rating_date,
            user_rating    = excluded.user_rating,
            tmdb_id        = excluded.tmdb_id,
            imdb_id        = excluded.imdb_id,
            genres         = excluded.genres,
            countries      = excluded.countries,
            languages      = excluded.languages,
            runtime        = excluded.runtime,
            directors      = excluded.directors,
            cast           = excluded.cast,
            tmdb_rating    = excluded.tmdb_rating,
            tmdb_votes     = excluded.tmdb_votes,
            imdb_rating    = excluded.imdb_rating,
            imdb_votes     = excluded.imdb_votes
    """, (
        movie.name,
        movie.year,
        movie.letterboxd_uri,
        movie.rating_date,
        movie.user_rating,
        movie.tmdb_id,
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

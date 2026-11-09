import sqlite3

from core.migrations import run_migrations
from core.config import DB_PATH


def get_connection():
    """Create and return a database connection with foreign keys enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def create_tables(conn):
    """Create all required tables, indexes, and views if they do not exist."""
    conn.executescript("""
        -- App metadata key-value store
        CREATE TABLE IF NOT EXISTS app_metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- Collections table
        CREATE TABLE IF NOT EXISTS collections (
            collection_id   INTEGER PRIMARY KEY,
            collection_name TEXT NOT NULL,
            total_movies    INTEGER,
            poster_path     TEXT,
            backdrop_path   TEXT,
            fetched_at      TEXT
        );

        -- Movies table
        CREATE TABLE IF NOT EXISTS movies (
            movie_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uri               TEXT UNIQUE NOT NULL,
            name              TEXT NOT NULL,
            year              INTEGER NOT NULL,
            rating            REAL,
            rated_date        TEXT,
            tmdb_id           INTEGER,
            imdb_id           TEXT,
            runtime           INTEGER,
            original_language TEXT,
            poster_path       TEXT,
            backdrop_path     TEXT,
            collection_id     INTEGER,
            fetch_status      TEXT NOT NULL DEFAULT 'pending', -- pending / ok / not_found / failed
            is_active         INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (collection_id) REFERENCES collections(collection_id) ON DELETE SET NULL
        );

        -- Active movies view (is_active = 1). Every stat reads from this.
        CREATE VIEW IF NOT EXISTS active_movies AS
            SELECT * FROM movies WHERE is_active = 1;

        -- IMDb ratings table (populated from TSV dataset)
        CREATE TABLE IF NOT EXISTS imdb_ratings (
            imdb_id TEXT PRIMARY KEY,
            rating  REAL,
            votes   INTEGER
        );

        -- People table (actors and directors)
        CREATE TABLE IF NOT EXISTS people (
            person_id     INTEGER PRIMARY KEY,
            name          TEXT NOT NULL,
            profile_paths TEXT,
            gender        INTEGER NOT NULL DEFAULT 0
        );

        -- Production companies table
        CREATE TABLE IF NOT EXISTS companies (
            company_id     INTEGER PRIMARY KEY,
            name           TEXT NOT NULL,
            logo_path      TEXT,
            origin_country TEXT
        );

        -- Countries table
        CREATE TABLE IF NOT EXISTS countries (
            country_code TEXT PRIMARY KEY,
            name         TEXT NOT NULL
        );

        -- Link tables
        CREATE TABLE IF NOT EXISTS movie_cast (
            movie_id      INTEGER NOT NULL,
            person_id     INTEGER NOT NULL,
            billing_order INTEGER,
            PRIMARY KEY (movie_id, person_id),
            FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE CASCADE
        );

        -- Index for fast cast billing queries
        CREATE INDEX IF NOT EXISTS idx_cast_movie_billing ON movie_cast(movie_id, billing_order);

        CREATE TABLE IF NOT EXISTS movie_directors (
            movie_id  INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            PRIMARY KEY (movie_id, person_id),
            FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS movie_genres (
            movie_id   INTEGER NOT NULL,
            genre_id   INTEGER NOT NULL,
            genre_name TEXT NOT NULL,
            PRIMARY KEY (movie_id, genre_id),
            FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS movie_countries (
            movie_id     INTEGER NOT NULL,
            country_code TEXT NOT NULL,
            PRIMARY KEY (movie_id, country_code),
            FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS movie_companies (
            movie_id   INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            PRIMARY KEY (movie_id, company_id),
            FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE,
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
        );

        -- Indexes for fast lookups
        CREATE INDEX IF NOT EXISTS idx_movies_uri ON movies(uri);
        CREATE INDEX IF NOT EXISTS idx_movies_name_year ON movies(name, year);
        CREATE INDEX IF NOT EXISTS idx_movies_tmdb_id ON movies(tmdb_id);
        CREATE INDEX IF NOT EXISTS idx_movies_fetch_status ON movies(fetch_status);
        CREATE INDEX IF NOT EXISTS idx_movies_is_active ON movies(is_active);
        CREATE INDEX IF NOT EXISTS idx_movie_genres_name ON movie_genres(genre_name);
        CREATE INDEX IF NOT EXISTS idx_movie_countries_code ON movie_countries(country_code);
        CREATE INDEX IF NOT EXISTS idx_movie_companies_company ON movie_companies(company_id);
    """)

    conn.commit()

    # Upgrade database if schema has changed
    run_migrations(conn)


def get_metadata(conn, key):
    """Retrieve a value from app_metadata."""
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_metadata WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


def set_metadata(conn, key, value):
    """Store or update a key-value pair in app_metadata."""
    conn.execute("""
        INSERT INTO app_metadata (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()


def find_movie_by_uri(conn, uri):
    """Query movie row by its Letterboxd URI.
    Returns tuple: (movie_id, name, year, rating, rated_date, uri) or None
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT movie_id, name, year, rating, rated_date, uri
        FROM movies
        WHERE uri = ?
        LIMIT 1
    """, (uri,))
    return cursor.fetchone()


def find_movie_by_name_year(conn, name, year):
    """Fallback query movie row by name and year (case-insensitive name).
    Returns tuple: (movie_id, name, year, rating, rated_date, uri) or None
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT movie_id, name, year, rating, rated_date, uri
        FROM movies
        WHERE LOWER(name) = LOWER(?) AND year = ?
        LIMIT 1
    """, (name, year))
    return cursor.fetchone()

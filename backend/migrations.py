from core.config import SCHEMA_VERSION


def _column_exists(conn, table, column):
    """Return True if 'column' exists in 'table'."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(conn, table):
    """Return True if 'table' exists in the database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cursor.fetchone() is not None


def _add_column(conn, table, column, definition):
    """ALTER TABLE ADD COLUMN only if the column is missing."""
    if _table_exists(conn, table) and not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _get_schema_version(conn):
    """Retrieve current schema version directly from app_metadata to avoid circular imports."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'")
        row = cursor.fetchone()
        return row[0] if row else "1.0.0"
    except Exception:
        return "1.0.0"


def _set_schema_version(conn, version):
    """Update current schema version directly in app_metadata."""
    conn.execute("""
        INSERT INTO app_metadata (key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (version,))


def _migrate_1_1_0(conn):
    """1.1.0: Cast gender, production companies, and countries tables.
    - Adds 'gender' column to 'people' table (default 0).
    - Ensures 'companies', 'countries', and 'movie_companies' tables and indexes exist.
    - Marks movies as pending so they can be re-enriched with production countries,
      expanded cast selection, gender, and production companies without deleting data.
    """
    # 1. Add gender column to people if missing
    _add_column(conn, "people", "gender", "INTEGER NOT NULL DEFAULT 0")

    # 2. Ensure new tables exist
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            company_id     INTEGER PRIMARY KEY,
            name           TEXT NOT NULL,
            logo_path      TEXT,
            origin_country TEXT
        );

        CREATE TABLE IF NOT EXISTS countries (
            country_code TEXT PRIMARY KEY,
            name         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS movie_companies (
            movie_id   INTEGER NOT NULL,
            company_id INTEGER NOT NULL,
            PRIMARY KEY (movie_id, company_id),
            FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE,
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_movie_companies_company ON movie_companies(company_id);
    """)

    # 3. Mark existing movies to be re-enriched with new metadata
    print("\n[MIGRATION 1.1.0] Marking active movies with 'ok' status as 'pending' for metadata re-enrichment...")
    conn.execute("UPDATE movies SET fetch_status = 'pending' WHERE fetch_status = 'ok'")


MIGRATIONS = [
    ("1.1.0", _migrate_1_1_0),
]


def _version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def run_migrations(conn):
    """Apply every migration newer than the stored schema_version, then stamp SCHEMA_VERSION."""
    current = _get_schema_version(conn)

    for version, migrate in MIGRATIONS:
        if _version_tuple(version) > _version_tuple(current):
            print(f"[DB] Migrating schema {current} -> {version}...")
            migrate(conn)
            _set_schema_version(conn, version)
            current = version

    _set_schema_version(conn, SCHEMA_VERSION)
    conn.commit()

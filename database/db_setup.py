import os
import sqlite3
import streamlit as st

try:
    import libsql
except ImportError:
    libsql = None

DB_PATH = os.path.join("data", "learning_system.db")


class _DictRowCursor:
    """Wraps libsql cursor results so rows support both row['col'] and row[0] access."""
    def __init__(self, cursor):
        self._cursor = cursor

    def _wrap_row(self, row):
        if row is None or not self._cursor.description:
            return row
        cols = [col[0] for col in self._cursor.description]
        return _DictRow(cols, row)

    def fetchone(self):
        return self._wrap_row(self._cursor.fetchone())

    def fetchall(self):
        return [self._wrap_row(r) for r in self._cursor.fetchall()]

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _DictRow(tuple):
    """Mimics sqlite3.Row for dict-key and index lookups."""
    def __new__(cls, cols, values):
        obj = super().__new__(cls, values)
        obj._mapping = dict(zip(cols, values))
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._mapping[key]
        return super().__getitem__(key)

    def keys(self):
        return self._mapping.keys()


class _TursoConnectionWrapper:
    """Provides standard sqlite3 context-manager and sync behavior over libsql."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        cur = self._conn.execute(sql, params)
        return _DictRowCursor(cur)

    def commit(self):
        self._conn.commit()
        self._conn.sync()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self._conn.rollback()


def _get_turso_credentials():
    url, token = None, None
    try:
        url = st.secrets.get("TURSO_DATABASE_URL")
        token = st.secrets.get("TURSO_AUTH_TOKEN")
    except Exception:
        pass
    url = url or os.getenv("TURSO_DATABASE_URL")
    token = token or os.getenv("TURSO_AUTH_TOKEN")
    return url, token


def get_connection():
    """Return a Turso cloud-synced connection if configured, else local SQLite."""
    os.makedirs("data", exist_ok=True)
    url, token = _get_turso_credentials()

    if url and token and libsql is not None:
        raw_conn = libsql.connect(DB_PATH, sync_url=url, auth_token=token)
        raw_conn.sync()
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        return _TursoConnectionWrapper(raw_conn)

    # Local fallback (Windows PC offline dev)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _ensure_column(conn, table_name: str, column_name: str, column_def: str):
    """Safely add a column to an existing STRICT table if it does not already exist."""
    existing_cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in existing_cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def};")


def init_db():
    """Initialize all core database tables and apply safe schema migrations."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            ) STRICT;
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                language TEXT NOT NULL,
                error_title TEXT NOT NULL,
                broken_code TEXT NOT NULL,
                error_message TEXT NOT NULL,
                ai_diagnosis TEXT NOT NULL,
                fixed_code TEXT,
                mastered INTEGER NOT NULL DEFAULT 0 CHECK (mastered IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            ) STRICT;
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                notes TEXT,
                total_pages INTEGER NOT NULL DEFAULT 1,
                pages_json TEXT NOT NULL DEFAULT '[]',
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT
            ) STRICT;
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                analysis TEXT NOT NULL,
                starter_code TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT
            ) STRICT;
        """)

        # Migrate existing Turso/SQLite tables safely if created prior to 7-day retention
        _ensure_column(conn, "documents", "total_pages", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "documents", "pages_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, "documents", "expires_at", "TEXT")
        _ensure_column(conn, "screenshots", "expires_at", "TEXT")
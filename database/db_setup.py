import os
import sqlite3

DB_PATH = os.path.join("data", "learning_system.db")

def get_connection() -> sqlite3.Connection:
    """Return a configured SQLite connection with row factory and pragmas enabled."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db():
    """Initialize all core database tables if they do not exist."""
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
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
            ) STRICT;
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                analysis TEXT NOT NULL,
                starter_code TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            ) STRICT;
        """)
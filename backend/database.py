import sqlite3
import os
from flask import g

# Resolve DB path from DATABASE_DIR if set (PaaS mounted volume, e.g. /data),
# otherwise fall back to THIS file's folder (backend/), not cwd.
DATABASE_DIR = os.getenv("DATABASE_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATABASE_DIR, exist_ok=True)
DATABASE_FILE = os.path.join(DATABASE_DIR, "ai_tutor.db")


def get_db():
    """Return a per-request SQLite connection stored on Flask's g object."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    """Close the DB connection at end of request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            email         TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS code_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            code       TEXT    NOT NULL,
            language   TEXT    NOT NULL,
            mode       TEXT    NOT NULL,
            result     TEXT,
            difficulty TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Using database at: {DATABASE_FILE}")


def init_challenge_table():
    """Create challenge_attempts table if not exists."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS challenge_attempts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            title        TEXT    NOT NULL,
            difficulty   TEXT    NOT NULL,
            code         TEXT    NOT NULL,
            score        INTEGER NOT NULL DEFAULT 0,
            total        INTEGER NOT NULL DEFAULT 0,
            passed       INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

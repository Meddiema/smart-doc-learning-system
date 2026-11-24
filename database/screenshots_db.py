import os
import time
from datetime import datetime, timedelta, timezone
from database.db_setup import get_connection, init_db

SCREENSHOT_RETENTION_DAYS = 7
DEFAULT_SCREENSHOT_DIR = os.path.join("uploads", "screenshots")
UTC_FMT = "%Y-%m-%d %H:%M:%S"


def purge_expired_screenshots(screenshot_dir: str = DEFAULT_SCREENSHOT_DIR) -> int:
    """Delete screenshot DB rows and local image files older than 7 days."""
    init_db()
    now_iso = datetime.now(timezone.utc).strftime(UTC_FMT)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, filename FROM screenshots
            WHERE (expires_at IS NOT NULL AND datetime(expires_at) < datetime(?))
               OR (expires_at IS NULL AND created_at IS NOT NULL AND datetime(created_at) < datetime(?, '-7 days'))
            """,
            (now_iso, now_iso),
        ).fetchall()

        if not rows:
            return 0

        for row in rows:
            fname = row["filename"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[1]
            fpath = os.path.join(screenshot_dir, os.path.basename(fname))
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        conn.execute(
            """
            DELETE FROM screenshots
            WHERE (expires_at IS NOT NULL AND datetime(expires_at) < datetime(?))
               OR (expires_at IS NULL AND created_at IS NOT NULL AND datetime(created_at) < datetime(?, '-7 days'))
            """,
            (now_iso, now_iso),
        )
        return len(rows)


def save_screenshot_record(
    filename: str,
    analysis: str,
    starter_code: str = "",
    retention_days: int = SCREENSHOT_RETENTION_DAYS,
) -> int:
    """Save a screenshot analysis to Turso/SQLite with a 7-day auto-expiration timestamp."""
    init_db()
    purge_expired_screenshots()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=retention_days)).strftime(UTC_FMT)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO screenshots (filename, analysis, starter_code, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (filename, analysis, starter_code, expires_at),
        )
        return cursor.lastrowid


def renew_screenshot_retention(
    screenshot_id: int,
    retention_days: int = SCREENSHOT_RETENTION_DAYS,
    screenshot_dir: str = DEFAULT_SCREENSHOT_DIR,
) -> str:
    """Extend a screenshot analysis retention window by another 7 days from now (UTC)."""
    init_db()
    purge_expired_screenshots(screenshot_dir=screenshot_dir)
    new_expires_at = (datetime.now(timezone.utc) + timedelta(days=retention_days)).strftime(UTC_FMT)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT filename FROM screenshots WHERE id = ?",
            (screenshot_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE screenshots
            SET expires_at = ?
            WHERE id = ?
            """,
            (new_expires_at, screenshot_id),
        )

    if row:
        fname = row["filename"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[0]
        if fname:
            fpath = os.path.join(screenshot_dir, os.path.basename(fname))
            if os.path.exists(fpath) and os.path.isfile(fpath):
                try:
                    now = time.time()
                    os.utime(fpath, (now, now))
                except Exception:
                    pass

    return new_expires_at


def get_all_screenshots() -> list[dict]:
    """Return all active (non-expired) screenshot records ordered newest first."""
    init_db()
    purge_expired_screenshots()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM screenshots ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def delete_screenshot_record(screenshot_id: int, filename: str = "", screenshot_dir: str = DEFAULT_SCREENSHOT_DIR):
    """Immediately delete a screenshot record from Turso/SQLite and remove its local file if present."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM screenshots WHERE id = ?", (screenshot_id,))
    if filename:
        fpath = os.path.join(screenshot_dir, os.path.basename(filename))
        if os.path.exists(fpath) and os.path.isfile(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
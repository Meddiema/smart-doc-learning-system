import json
from datetime import datetime, timedelta, timezone
from database.db_setup import get_connection

DOCUMENT_RETENTION_DAYS = 7


def purge_expired_documents() -> list[str]:
    """Delete documents past their 7-day expires_at timestamp. Returns deleted filenames."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT filename FROM documents
            WHERE (expires_at IS NOT NULL AND datetime(expires_at) < datetime(?))
               OR (expires_at IS NULL AND uploaded_at IS NOT NULL AND datetime(uploaded_at) < datetime(?, '-7 days'))
            """,
            (now_iso, now_iso),
        ).fetchall()
        expired_files = [row["filename"] for row in rows]

        if expired_files:
            conn.execute(
                """
                DELETE FROM documents
                WHERE (expires_at IS NOT NULL AND datetime(expires_at) < datetime(?))
                   OR (expires_at IS NULL AND uploaded_at IS NOT NULL AND datetime(uploaded_at) < datetime(?, '-7 days'))
                """,
                (now_iso, now_iso),
            )
        return expired_files


def save_document_to_turso(
    filename: str,
    pages: list[dict],
    notes: str = "",
    retention_days: int = DOCUMENT_RETENTION_DAYS,
):
    """Save or refresh extracted PDF pages in Turso with a 7-day auto-expiration timestamp."""
    purge_expired_documents()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
    pages_json = json.dumps(pages)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents (filename, notes, total_pages, pages_json, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                notes = excluded.notes,
                total_pages = excluded.total_pages,
                pages_json = excluded.pages_json,
                uploaded_at = datetime('now'),
                expires_at = excluded.expires_at
            """,
            (filename, notes, len(pages), pages_json, expires_at),
        )


def list_turso_documents() -> list[dict]:
    """Return metadata for all active (non-expired) documents stored in Turso."""
    purge_expired_documents()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, notes, total_pages, uploaded_at, expires_at
            FROM documents
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_turso_document_pages(filename: str) -> list[dict]:
    """Retrieve the extracted page list for a given PDF filename from Turso."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT pages_json FROM documents WHERE filename = ?",
            (filename,),
        ).fetchone()
        if row and row["pages_json"]:
            try:
                return json.loads(row["pages_json"])
            except Exception:
                return []
    return []


def delete_turso_document(filename: str):
    """Immediately remove a document record from Turso."""
    with get_connection() as conn:
        conn.execute("DELETE FROM documents WHERE filename = ?", (filename,))
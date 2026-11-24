import json
import math
from datetime import datetime, timedelta, timezone
from database.db_setup import get_connection

DOCUMENT_RETENTION_DAYS = 7
UTC_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_utc_timestamp(ts_str: str | None) -> datetime | None:
    """Parse SQLite/ISO UTC timestamp strings safely into timezone-aware UTC datetimes."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    cleaned = ts_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    for fmt in (UTC_FMT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(cleaned[:26], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def get_document_days_remaining(
    expires_at: str | None,
    uploaded_at: str | None = None,
    retention_days: int = DOCUMENT_RETENTION_DAYS,
) -> dict:
    """Return remaining time metadata for countdown badges and expiry warnings."""
    now_utc = datetime.now(timezone.utc)
    exp_dt = _parse_utc_timestamp(expires_at)

    if exp_dt is None:
        up_dt = _parse_utc_timestamp(uploaded_at)
        if up_dt is not None:
            exp_dt = up_dt + timedelta(days=retention_days)

    if exp_dt is None:
        return {
            "days_left": retention_days,
            "hours_left": retention_days * 24,
            "expires_label": f"{retention_days}d TTL",
            "badge": f"⏳ {retention_days}d left",
            "is_expiring_soon": False,
        }

    delta = exp_dt - now_utc
    total_seconds = max(0.0, delta.total_seconds())
    hours_left = math.ceil(total_seconds / 3600.0) if total_seconds > 0 else 0
    days_left = math.ceil(total_seconds / 86400.0) if total_seconds > 0 else 0

    if total_seconds <= 0:
        badge = "⚠️ Expired"
    elif hours_left < 24:
        badge = f"⚠️ {hours_left}h left"
    else:
        badge = f"⏳ {days_left}d left"

    return {
        "days_left": days_left,
        "hours_left": hours_left,
        "expires_label": exp_dt.strftime("%b %d, %H:%M UTC"),
        "badge": badge,
        "is_expiring_soon": 0 < hours_left <= 48,
    }


def purge_expired_documents() -> list[str]:
    """Delete documents past their 7-day expires_at timestamp. Returns deleted filenames."""
    now_iso = datetime.now(timezone.utc).strftime(UTC_FMT)
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
    now_utc = datetime.now(timezone.utc)
    expires_at = (now_utc + timedelta(days=retention_days)).strftime(UTC_FMT)
    uploaded_at = now_utc.strftime(UTC_FMT)
    pages_json = json.dumps(pages)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO documents (filename, notes, total_pages, pages_json, uploaded_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                notes = excluded.notes,
                total_pages = excluded.total_pages,
                pages_json = excluded.pages_json,
                uploaded_at = excluded.uploaded_at,
                expires_at = excluded.expires_at
            """,
            (filename, notes, len(pages), pages_json, uploaded_at, expires_at),
        )


def renew_document_retention(filename: str, retention_days: int = DOCUMENT_RETENTION_DAYS) -> str:
    """Extend a document's retention window by another 7 days from now (UTC)."""
    purge_expired_documents()
    new_expires_at = (datetime.now(timezone.utc) + timedelta(days=retention_days)).strftime(UTC_FMT)
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE documents
            SET expires_at = ?
            WHERE filename = ?
            """,
            (new_expires_at, filename),
        )
    return new_expires_at


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
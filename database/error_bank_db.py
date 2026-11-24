import math
from datetime import datetime, timedelta, timezone
from database.db_setup import get_connection, init_db

ERROR_RETENTION_DAYS = 15
UTC_FMT = "%Y-%m-%d %H:%M:%S"
_EXPIRES_COL_CACHE: bool | None = None


def _parse_utc_timestamp(ts_str: str | None) -> datetime | None:
    """Parse SQLite/ISO UTC timestamp strings safely into timezone-aware UTC datetimes."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    cleaned = ts_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        pass

    for fmt in (UTC_FMT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(cleaned[:26], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _has_expires_at_column(conn) -> bool:
    """Check whether error_bank has an expires_at column (compatible with SQLite and Turso/libSQL)."""
    global _EXPIRES_COL_CACHE
    if _EXPIRES_COL_CACHE is not None:
        return _EXPIRES_COL_CACHE

    try:
        conn.execute("SELECT expires_at FROM error_bank LIMIT 1").fetchone()
        _EXPIRES_COL_CACHE = True
    except Exception:
        _EXPIRES_COL_CACHE = False

    return _EXPIRES_COL_CACHE


def get_error_retention_info(error_row: dict, retention_days: int = ERROR_RETENTION_DAYS) -> dict:
    """Return countdown badge and expiry metadata for an Error Bank item."""
    now_utc = datetime.now(timezone.utc)
    exp_dt = _parse_utc_timestamp(error_row.get("expires_at"))

    if exp_dt is None:
        created_dt = _parse_utc_timestamp(error_row.get("created_at"))
        if created_dt is not None:
            exp_dt = created_dt + timedelta(days=retention_days)

    if exp_dt is None:
        return {
            "days_left": retention_days,
            "hours_left": retention_days * 24,
            "expires_label": f"{retention_days}d TTL",
            "badge": f"⏳ {retention_days}d left",
            "is_expiring_soon": False,
        }

    remaining_secs = max(0.0, (exp_dt - now_utc).total_seconds())
    hours_left = math.ceil(remaining_secs / 3600.0) if remaining_secs > 0 else 0
    days_left = math.ceil(remaining_secs / 86400.0) if remaining_secs > 0 else 0

    if remaining_secs <= 0:
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
        "is_expiring_soon": 0 < hours_left <= 72,
    }


def purge_expired_errors(days: int = ERROR_RETENTION_DAYS) -> int:
    """Automatically delete Personal Error Bank entries older than `days` (default 15 days)."""
    init_db()
    interval = f"-{int(days)} days"
    now_iso = datetime.now(timezone.utc).strftime(UTC_FMT)
    with get_connection() as conn:
        has_exp = _has_expires_at_column(conn)
        if has_exp:
            where_clause = (
                "(expires_at IS NOT NULL AND datetime(expires_at) < datetime(?)) "
                "OR (expires_at IS NULL AND created_at IS NOT NULL AND datetime(created_at) < datetime(?, ?))"
            )
            params = (now_iso, now_iso, interval)
        else:
            where_clause = "created_at IS NOT NULL AND datetime(created_at) < datetime(?, ?)"
            params = (now_iso, interval)

        row = conn.execute(f"SELECT COUNT(*) FROM error_bank WHERE {where_clause}", params).fetchone()
        expired_count = row[0] if row else 0
        if expired_count > 0:
            conn.execute(f"DELETE FROM error_bank WHERE {where_clause}", params)
        return expired_count


def add_error(
    language: str,
    error_title: str,
    broken_code: str,
    error_message: str,
    ai_diagnosis: str,
    fixed_code: str = "",
    retention_days: int = ERROR_RETENTION_DAYS,
) -> int:
    init_db()
    purge_expired_errors(retention_days)
    now_utc = datetime.now(timezone.utc)
    created_iso = now_utc.strftime(UTC_FMT)
    expires_iso = (now_utc + timedelta(days=retention_days)).strftime(UTC_FMT)

    with get_connection() as conn:
        if _has_expires_at_column(conn):
            cursor = conn.execute(
                """
                INSERT INTO error_bank (
                    language, error_title, broken_code, error_message, ai_diagnosis, fixed_code, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (language, error_title, broken_code, error_message, ai_diagnosis, fixed_code, created_iso, expires_iso),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO error_bank (
                    language, error_title, broken_code, error_message, ai_diagnosis, fixed_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (language, error_title, broken_code, error_message, ai_diagnosis, fixed_code, created_iso),
            )
        return cursor.lastrowid


def renew_error_retention(error_id: int, retention_days: int = ERROR_RETENTION_DAYS) -> str:
    """Extend an Error Bank entry's retention window by another 15 days from now (UTC)."""
    init_db()
    purge_expired_errors(retention_days)
    now_utc = datetime.now(timezone.utc)
    created_iso = now_utc.strftime(UTC_FMT)
    expires_iso = (now_utc + timedelta(days=retention_days)).strftime(UTC_FMT)

    with get_connection() as conn:
        if _has_expires_at_column(conn):
            conn.execute(
                """
                UPDATE error_bank
                SET created_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (created_iso, expires_iso, error_id),
            )
        else:
            conn.execute(
                """
                UPDATE error_bank
                SET created_at = ?
                WHERE id = ?
                """,
                (created_iso, error_id),
            )
    return expires_iso


def get_all_errors(search_query: str = "", only_unmastered: bool = False) -> list[dict]:
    init_db()
    purge_expired_errors()
    clauses = []
    params = []

    if search_query.strip():
        clauses.append("(error_title LIKE ? OR error_message LIKE ? OR language LIKE ?)")
        wildcard = f"%{search_query.strip()}%"
        params.extend([wildcard, wildcard, wildcard])

    if only_unmastered:
        clauses.append("mastered = 0")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM error_bank {where_sql} ORDER BY id DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def toggle_mastered(error_id: int, mastered: bool):
    init_db()
    with get_connection() as conn:
        conn.execute(
            "UPDATE error_bank SET mastered = ? WHERE id = ?",
            (1 if mastered else 0, error_id),
        )


def delete_error(error_id: int):
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM error_bank WHERE id = ?", (error_id,))


def purge_all_errors():
    """Manually clear all entries from the Personal Error Bank."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM error_bank")


def get_error_stats() -> dict:
    init_db()
    purge_expired_errors()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM error_bank").fetchone()[0]
        mastered = conn.execute("SELECT COUNT(*) FROM error_bank WHERE mastered = 1").fetchone()[0]
        return {"total": total, "mastered": mastered, "active": total - mastered}
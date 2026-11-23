from database.db_setup import get_connection

ERROR_RETENTION_DAYS = 15


def purge_expired_errors(days: int = ERROR_RETENTION_DAYS) -> int:
    """Automatically delete Personal Error Bank entries older than `days` (default 15 days)."""
    interval = f"-{int(days)} days"
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM error_bank WHERE created_at IS NOT NULL AND datetime(created_at) < datetime('now', ?)",
            (interval,),
        ).fetchone()
        expired_count = row[0] if row else 0
        if expired_count > 0:
            conn.execute(
                "DELETE FROM error_bank WHERE created_at IS NOT NULL AND datetime(created_at) < datetime('now', ?)",
                (interval,),
            )
        return expired_count


def add_error(
    language: str,
    error_title: str,
    broken_code: str,
    error_message: str,
    ai_diagnosis: str,
    fixed_code: str = "",
) -> int:
    purge_expired_errors()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO error_bank (language, error_title, broken_code, error_message, ai_diagnosis, fixed_code)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (language, error_title, broken_code, error_message, ai_diagnosis, fixed_code),
        )
        return cursor.lastrowid


def get_all_errors(search_query: str = "", only_unmastered: bool = False) -> list[dict]:
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
    with get_connection() as conn:
        conn.execute(
            "UPDATE error_bank SET mastered = ? WHERE id = ?",
            (1 if mastered else 0, error_id),
        )


def delete_error(error_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM error_bank WHERE id = ?", (error_id,))


def purge_all_errors():
    """Manually clear all entries from the Personal Error Bank."""
    with get_connection() as conn:
        conn.execute("DELETE FROM error_bank")


def get_error_stats() -> dict:
    purge_expired_errors()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM error_bank").fetchone()[0]
        mastered = conn.execute("SELECT COUNT(*) FROM error_bank WHERE mastered = 1").fetchone()[0]
        return {"total": total, "mastered": mastered, "active": total - mastered}
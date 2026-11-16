from database.db_setup import get_connection, init_db

def save_screenshot_record(filename: str, analysis: str, starter_code: str = "") -> int:
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO screenshots (filename, analysis, starter_code)
            VALUES (?, ?, ?)
            """,
            (filename, analysis, starter_code)
        )
        return cursor.lastrowid

def get_all_screenshots() -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM screenshots ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]
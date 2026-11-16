import hashlib
import hmac
import os
import sqlite3
from database.db_setup import get_connection, init_db

def _hash_password(password: str, salt: bytes) -> str:
    """Derive a salted PBKDF2-HMAC-SHA256 hex digest."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return dk.hex()

def register_user(username: str, password: str) -> tuple[bool, str]:
    """Create a new user account. Returns (success, message)."""
    init_db()
    clean_user = username.strip().lower()
    if len(clean_user) < 3:
        return False, "Username must be at least 3 characters long."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."

    salt = os.urandom(16)
    pwd_hash = _hash_password(password, salt)

    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (clean_user, pwd_hash, salt.hex())
            )
        return True, "Account created! You can now log in."
    except sqlite3.IntegrityError:
        return False, "That username is already taken."

def authenticate_user(username: str, password: str) -> dict | None:
    """Verify username and password. Returns user dict if valid, else None."""
    init_db()
    clean_user = username.strip().lower()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
            (clean_user,)
        ).fetchone()

    if not row:
        return None

    salt = bytes.fromhex(row["salt"])
    expected_hash = row["password_hash"]
    actual_hash = _hash_password(password, salt)

    if hmac.compare_digest(expected_hash, actual_hash):
        return {"id": row["id"], "username": row["username"]}
    return None
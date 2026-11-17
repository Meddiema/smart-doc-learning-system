import hmac
import os
import time
import streamlit as st
from database.db_setup import get_connection

MAX_REGISTERED_USERS = 15


def get_expected_invite_code() -> str:
    """Retrieve APP_INVITE_CODE from Streamlit secrets or environment variables."""
    code = ""
    try:
        code = st.secrets.get("APP_INVITE_CODE", "")
    except Exception:
        pass
    return (code or os.getenv("APP_INVITE_CODE", "")).strip()


def verify_invite_code(submitted_code: str) -> bool:
    """Check submitted access code safely against APP_INVITE_CODE."""
    expected = get_expected_invite_code()
    if not expected:
        return True
    return hmac.compare_digest(submitted_code.strip(), expected)


def can_register_new_user() -> tuple[bool, str]:
    """Enforce a hard ceiling on total registered accounts to protect daily API quota."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM users;").fetchone()
        total = row["total"] if row else 0
    if total >= MAX_REGISTERED_USERS:
        return False, f"Registration closed: maximum limit of {MAX_REGISTERED_USERS} authorized users reached."
    return True, ""


def enforce_user_cooldown(cooldown_seconds: int = 20):
    """Stop rapid button-spamming within a single user session."""
    now = time.time()
    last_call = st.session_state.get("last_ai_call_ts", 0.0)
    remaining = cooldown_seconds - (now - last_call)
    if remaining > 0:
        st.warning(f"⏳ Please wait {int(remaining) + 1} seconds before making another AI request.")
        st.stop()
    st.session_state["last_ai_call_ts"] = now
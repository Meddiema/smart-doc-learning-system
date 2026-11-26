import os
import time
import threading
from collections import deque
from datetime import datetime, timezone
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# Adjust these limits to protect your free-tier Gemini quota
MAX_REQUESTS_PER_MINUTE = 8          # Global RPM cap across ALL users per 60s
MAX_REQUESTS_PER_DAY = 180           # Global RPD cap across ALL users per UTC day
MIN_SECONDS_BETWEEN_USER_CALLS = 15  # Per-user cooldown to block rapid clicking
MAX_INPUT_CHARS = 32_000             # Safety ceiling per prompt payload


@st.cache_resource
def _get_global_rate_limiter():
    """Shared across ALL users and browser sessions on the Streamlit server."""
    return {
        "lock": threading.Lock(),
        "timestamps": deque(),
        "utc_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "daily_count": 0,
        "daily_exhausted": False,
    }


def _roll_utc_day_if_needed(limiter: dict) -> None:
    """Reset the daily counter automatically at 00:00 UTC."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if limiter.get("utc_day") != today:
        limiter["utc_day"] = today
        limiter["daily_count"] = 0
        limiter["daily_exhausted"] = False


class AIClient:
    def __init__(self):
        api_key = None
        try:
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
        api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .streamlit/secrets.toml or environment variables")

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=25_000)  # 25s max per request
        )
        self.models = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

    @staticmethod
    def get_quota_status() -> dict:
        """Return live RPM and daily quota availability without consuming a slot."""
        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            now = time.time()
            _roll_utc_day_if_needed(limiter)
            while limiter["timestamps"] and now - limiter["timestamps"][0] >= 60.0:
                limiter["timestamps"].popleft()

            rpm_used = len(limiter["timestamps"])
            rpm_left = max(0, MAX_REQUESTS_PER_MINUTE - rpm_used)
            reset_in = int(60.0 - (now - limiter["timestamps"][0])) + 1 if limiter["timestamps"] else 0
            daily_used = limiter["daily_count"]
            daily_left = 0 if limiter["daily_exhausted"] else max(0, MAX_REQUESTS_PER_DAY - daily_used)

            return {
                "rpm_used": rpm_used,
                "rpm_limit": MAX_REQUESTS_PER_MINUTE,
                "rpm_left": rpm_left,
                "rpm_reset_in": reset_in,
                "daily_used": daily_used,
                "daily_limit": MAX_REQUESTS_PER_DAY,
                "daily_left": daily_left,
                "daily_exhausted": limiter["daily_exhausted"],
            }

    @classmethod
    def can_run_pipeline(cls, calls_needed: int) -> tuple[bool, str]:
        """Pre-flight check before multi-call pipelines (like Deep Multi-Pass synthesis)."""
        needed = max(1, int(calls_needed))
        status = cls.get_quota_status()

        if status["daily_exhausted"] or status["daily_left"] < needed:
            return (
                False,
                f"🛑 Daily quota protection: this action needs {needed} AI call(s), but only "
                f"{status['daily_left']} daily call(s) remain today. Use **Fast Overview** or a smaller page range.",
            )

        if status["rpm_left"] < needed:
            return (
                False,
                f"🛑 Burst protection: this action needs {needed} AI call(s), but only "
                f"{status['rpm_left']}/{status['rpm_limit']} RPM slots are free right now. "
                f"Wait ~{status['rpm_reset_in']}s or switch to **Fast Overview** (1 call).",
            )

        return True, ""

    def _check_and_reserve_slot(self, bypass_user_cooldown: bool = False) -> tuple[bool, str]:
        """
        Blocks rapid per-user clicks (unless bypassed internally for multi-step pipelines)
        AND enforces both server-wide RPM and daily RPD ceilings BEFORE sending any request to Gemini.
        """
        now = time.time()

        # 1. Per-user rapid-click guard (blocks double-clicks / button spam)
        if not bypass_user_cooldown:
            try:
                last_user_call = st.session_state.get("_last_ai_request_ts", 0.0)
                user_wait = MIN_SECONDS_BETWEEN_USER_CALLS - (now - last_user_call)
                if user_wait > 0:
                    return (
                        False,
                        f"🛑 Slow down: please wait {int(user_wait) + 1} seconds before sending another request.",
                    )
            except Exception:
                pass

        # 2. Global server-wide per-minute + per-day guard
        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            now = time.time()
            _roll_utc_day_if_needed(limiter)

            if limiter["daily_exhausted"] or limiter["daily_count"] >= MAX_REQUESTS_PER_DAY:
                return (
                    False,
                    f"🛑 Daily AI quota cap ({MAX_REQUESTS_PER_DAY} requests/day) reached to protect your API key. "
                    "Use zero-API features (PDF search, offline cheat-sheet, local quiz grading) until tomorrow.",
                )

            while limiter["timestamps"] and now - limiter["timestamps"][0] >= 60.0:
                limiter["timestamps"].popleft()

            if len(limiter["timestamps"]) >= MAX_REQUESTS_PER_MINUTE:
                reset_in = int(60.0 - (now - limiter["timestamps"][0])) + 1
                return (
                    False,
                    f"🛑 Rate limit protection active: server quota is full for this minute. Try again in {reset_in}s.",
                )

            # Reserve slot and record counters
            limiter["timestamps"].append(now)
            limiter["daily_count"] += 1

        try:
            st.session_state["_last_ai_request_ts"] = now
        except Exception:
            pass

        return True, ""

    @staticmethod
    def _sanitize_contents(contents):
        """Clamp oversized text strings to prevent accidental token spikes."""
        if isinstance(contents, str) and len(contents) > MAX_INPUT_CHARS:
            return contents[:MAX_INPUT_CHARS] + "\n\n[Truncated to protect token quota]"
        if isinstance(contents, list):
            sanitized = []
            for item in contents:
                if isinstance(item, str) and len(item) > MAX_INPUT_CHARS:
                    sanitized.append(item[:MAX_INPUT_CHARS] + "\n\n[Truncated to protect token quota]")
                else:
                    sanitized.append(item)
            return sanitized
        return contents

    def _generate_with_retry(
        self,
        contents,
        system_instruction: str = None,
        max_retries: int = 2,
        bypass_user_cooldown: bool = False,
    ) -> str:
        """Blocks rapid requests up front, then calls Gemini with fast failover."""
        allowed, block_message = self._check_and_reserve_slot(
            bypass_user_cooldown=bypass_user_cooldown
        )
        if not allowed:
            return block_message

        safe_contents = self._sanitize_contents(contents)
        config = (
            types.GenerateContentConfig(system_instruction=system_instruction)
            if system_instruction
            else None
        )
        last_error = ""

        for model_name in self.models:
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=safe_contents,
                        config=config
                    )
                    return response.text or "⚠️ Empty response returned from model."
                except Exception as e:
                    last_error = str(e)
                    # Fail fast if Google indicates a daily quota exhaustion (retrying won't help)
                    if "PerDay" in last_error or "GenerateRequestsPerDay" in last_error:
                        limiter = _get_global_rate_limiter()
                        with limiter["lock"]:
                            limiter["daily_exhausted"] = True
                        return "🛑 Upstream Gemini daily free-tier quota reached. Try again after daily quota reset."

                    if any(code in last_error for code in ("503", "UNAVAILABLE", "429", "DEADLINE", "timeout")):
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return f"⚠️ AI Error: {last_error}"

        return f"⚠️ AI Error (after retries): {last_error}"

    def ask(
        self,
        prompt: str,
        system_instruction: str = None,
        bypass_user_cooldown: bool = False,
    ) -> str:
        return self._generate_with_retry(
            contents=prompt,
            system_instruction=system_instruction,
            bypass_user_cooldown=bypass_user_cooldown,
        )

    def ask_with_image(
        self,
        prompt: str,
        image: Image.Image,
        system_instruction: str = None,
        bypass_user_cooldown: bool = False,
    ) -> str:
        return self._generate_with_retry(
            contents=[image, prompt],
            system_instruction=system_instruction,
            bypass_user_cooldown=bypass_user_cooldown,
        )
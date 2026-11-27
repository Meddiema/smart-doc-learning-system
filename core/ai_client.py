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
KEY_429_COOLDOWN_SECONDS = 65        # Cooldown before retrying a key that hit RPM 429


def _load_api_keys() -> list[str]:
    """Load 1..N Gemini API keys from Streamlit secrets or environment variables."""
    candidates: list[str] = []

    def _add_raw(val):
        if not val:
            return
        if isinstance(val, (list, tuple)):
            for item in val:
                _add_raw(item)
            return
        for part in str(val).replace("\n", ",").split(","):
            cleaned = part.strip().strip('"').strip("'")
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

    secret_names = (
        "GEMINI_API_KEYS",
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_1",
        "GEMINI_API_KEY_2",
        "GEMINI_API_KEY_3",
    )
    for name in secret_names:
        try:
            _add_raw(st.secrets.get(name))
        except Exception:
            pass
        _add_raw(os.getenv(name))

    return candidates


@st.cache_resource
def _get_global_rate_limiter():
    """Shared across ALL users and browser sessions on the Streamlit server."""
    keys = _load_api_keys()
    return {
        "lock": threading.Lock(),
        "timestamps": deque(),
        "utc_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "daily_count": 0,
        "daily_exhausted": False,
        "keys": keys,
        "active_key_idx": 0,
        "key_exhausted_day": {i: False for i in range(len(keys))},
        "key_cooldown_until": {i: 0.0 for i in range(len(keys))},
    }


def _roll_utc_day_if_needed(limiter: dict) -> None:
    """Reset the daily counter and per-key daily exhaustion flags at 00:00 UTC."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if limiter.get("utc_day") != today:
        limiter["utc_day"] = today
        limiter["daily_count"] = 0
        limiter["daily_exhausted"] = False
        for idx in range(len(limiter.get("keys", []))):
            limiter["key_exhausted_day"][idx] = False


class AIClient:
    def __init__(self):
        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            current_keys = _load_api_keys()
            if current_keys and current_keys != limiter.get("keys"):
                limiter["keys"] = current_keys
                limiter["active_key_idx"] = 0
                limiter["key_exhausted_day"] = {i: False for i in range(len(current_keys))}
                limiter["key_cooldown_until"] = {i: 0.0 for i in range(len(current_keys))}
            keys = list(limiter.get("keys") or [])

        if not keys:
            raise ValueError(
                "No Gemini API key found. Set GEMINI_API_KEY (and optionally GEMINI_API_KEY_2, GEMINI_API_KEY_3) "
                "in .streamlit/secrets.toml or environment variables."
            )

        self.api_keys = keys
        self.models = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
        self._clients: dict[int, genai.Client] = {}

    def _get_client_for_key(self, key_idx: int) -> genai.Client:
        if key_idx not in self._clients:
            self._clients[key_idx] = genai.Client(
                api_key=self.api_keys[key_idx],
                http_options=types.HttpOptions(timeout=25_000),
            )
        return self._clients[key_idx]

    @staticmethod
    def _ordered_key_indices(limiter: dict, now: float) -> list[int]:
        """Return usable key indices starting from active_key_idx."""
        keys = limiter.get("keys") or []
        n = len(keys)
        if n == 0:
            return []
        start = limiter.get("active_key_idx", 0) % n
        ordered = [(start + offset) % n for offset in range(n)]
        usable = [
            idx for idx in ordered
            if not limiter["key_exhausted_day"].get(idx, False)
            and now >= limiter["key_cooldown_until"].get(idx, 0.0)
        ]
        if not usable:
            usable = [
                idx for idx in ordered
                if not limiter["key_exhausted_day"].get(idx, False)
            ]
        return usable

    @staticmethod
    def get_quota_status() -> dict:
        """Return live RPM, daily quota, and active key availability without consuming a slot."""
        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            now = time.time()
            _roll_utc_day_if_needed(limiter)
            while limiter["timestamps"] and now - limiter["timestamps"][0] >= 60.0:
                limiter["timestamps"].popleft()

            keys = limiter.get("keys") or []
            total_keys = len(keys)
            active_idx = (limiter.get("active_key_idx", 0) % total_keys) if total_keys else 0
            usable_keys = len(AIClient._ordered_key_indices(limiter, now))

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
                "active_key_num": active_idx + 1 if total_keys else 0,
                "total_keys": total_keys,
                "usable_keys": usable_keys,
            }

    @classmethod
    def can_run_pipeline(cls, calls_needed: int) -> tuple[bool, str]:
        """Pre-flight check before multi-call pipelines."""
        needed = max(1, int(calls_needed))
        status = cls.get_quota_status()

        if status["total_keys"] > 0 and status["usable_keys"] == 0:
            return (
                False,
                f"🛑 All {status['total_keys']} configured Gemini API key(s) have hit their daily quota for today. "
                "Add a fresh key or try again after the daily quota reset.",
            )

        if status["daily_exhausted"] or status["daily_left"] < needed:
            return (
                False,
                f"🛑 Daily quota protection: this action needs {needed} AI call(s), but only "
                f"{status['daily_left']} daily call(s) remain today. Use a smaller page range.",
            )

        if status["rpm_left"] < needed:
            return (
                False,
                f"🛑 Burst protection: this action needs {needed} AI call(s), but only "
                f"{status['rpm_left']}/{status['rpm_limit']} RPM slots are free right now. "
                f"Wait ~{status['rpm_reset_in']}s before retrying.",
            )

        return True, ""

    def _check_and_reserve_slot(self, bypass_user_cooldown: bool = False) -> tuple[bool, str]:
        """Enforce per-user cooldown plus server-wide RPM and daily RPD ceilings."""
        now = time.time()

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

        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            now = time.time()
            _roll_utc_day_if_needed(limiter)

            if limiter.get("keys") and len(AIClient._ordered_key_indices(limiter, now)) == 0:
                limiter["daily_exhausted"] = True
                return (
                    False,
                    "🛑 All configured Gemini API keys have reached their daily quota. "
                    "Use zero-API features (PDF search, offline cheat-sheet, local quiz grading) until quota resets.",
                )

            if limiter["daily_exhausted"] or limiter["daily_count"] >= MAX_REQUESTS_PER_DAY:
                return (
                    False,
                    f"🛑 Daily AI quota cap ({MAX_REQUESTS_PER_DAY} requests/day) reached to protect your API keys. "
                    "Use zero-API features until tomorrow.",
                )

            while limiter["timestamps"] and now - limiter["timestamps"][0] >= 60.0:
                limiter["timestamps"].popleft()

            if len(limiter["timestamps"]) >= MAX_REQUESTS_PER_MINUTE:
                reset_in = int(60.0 - (now - limiter["timestamps"][0])) + 1
                return (
                    False,
                    f"🛑 Rate limit protection active: server quota is full for this minute. Try again in {reset_in}s.",
                )

            limiter["timestamps"].append(now)
            limiter["daily_count"] += 1

        try:
            st.session_state["_last_ai_request_ts"] = now
        except Exception:
            pass

        return True, ""

    @staticmethod
    def _release_failed_daily_slot() -> None:
        """Refund the local daily counter if upstream rejected the call across all keys."""
        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            if limiter["daily_count"] > 0:
                limiter["daily_count"] -= 1

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

    @staticmethod
    def _record_key_failure(key_idx: int, err_text: str) -> tuple[bool, bool]:
        """
        Update state for a failing key.
        Returns (should_switch_key, should_retry_same_key).
        """
        limiter = _get_global_rate_limiter()
        upper = err_text.upper()
        is_daily = "PERDAY" in upper or "GENERATEREQUESTSPERDAY" in upper
        is_quota_or_rate = (
            is_daily
            or "429" in upper
            or "RESOURCE_EXHAUSTED" in upper
            or "QUOTA" in upper
        )

        with limiter["lock"]:
            n = len(limiter.get("keys") or [])
            if is_daily:
                limiter["key_exhausted_day"][key_idx] = True
                for step in range(1, n + 1):
                    cand = (key_idx + step) % n
                    if not limiter["key_exhausted_day"].get(cand, False):
                        limiter["active_key_idx"] = cand
                        break
                if all(limiter["key_exhausted_day"].get(i, False) for i in range(n)):
                    limiter["daily_exhausted"] = True
                return True, False

            if is_quota_or_rate:
                limiter["key_cooldown_until"][key_idx] = time.time() + KEY_429_COOLDOWN_SECONDS
                if n > 1:
                    limiter["active_key_idx"] = (key_idx + 1) % n
                    return True, False
                return False, True

        return False, False

    def _generate_with_retry(
        self,
        contents,
        system_instruction: str = None,
        max_retries: int = 2,
        bypass_user_cooldown: bool = False,
    ) -> str:
        """Blocks rapid requests up front, rotates across available keys on quota/429, and fails over models."""
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

        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            key_order = self._ordered_key_indices(limiter, time.time()) or list(range(len(self.api_keys)))

        last_error = ""

        for key_idx in key_order:
            client = self._get_client_for_key(key_idx)
            switch_key = False

            for model_name in self.models:
                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=safe_contents,
                            config=config,
                        )
                        with limiter["lock"]:
                            limiter["active_key_idx"] = key_idx
                        return response.text or "⚠️ Empty response returned from model."
                    except Exception as e:
                        last_error = str(e)
                        should_switch, should_retry = self._record_key_failure(key_idx, last_error)
                        if should_switch:
                            switch_key = True
                            break
                        if should_retry or any(
                            code in last_error for code in ("503", "UNAVAILABLE", "429", "DEADLINE", "timeout")
                        ):
                            time.sleep(0.8 * (attempt + 1))
                            continue
                        self._release_failed_daily_slot()
                        return f"⚠️ AI Error (Key #{key_idx + 1}): {last_error}"

                if switch_key:
                    break

        self._release_failed_daily_slot()
        status = self.get_quota_status()
        if status["total_keys"] > 0 and status["usable_keys"] == 0:
            return (
                f"🛑 All {status['total_keys']} configured Gemini API key(s) hit daily free-tier quota limits. "
                f"Detail: {last_error[:180]}"
            )

        return f"⚠️ AI Error across {status['total_keys']} key(s): {last_error[:200]}"

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
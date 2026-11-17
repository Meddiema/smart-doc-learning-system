import os
import time
import threading
from collections import deque
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# Adjust these two limits to protect your free-tier Gemini quota
MAX_REQUESTS_PER_MINUTE = 8          # Global cap across ALL users per 60s
MIN_SECONDS_BETWEEN_USER_CALLS = 15  # Per-user cooldown to block rapid clicking


@st.cache_resource
def _get_global_rate_limiter():
    """Shared across ALL users and browser sessions on the Streamlit server."""
    return {
        "lock": threading.Lock(),
        "timestamps": deque(),
    }


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

    def _check_and_reserve_slot(self) -> tuple[bool, str]:
        """
        Blocks rapid per-user clicks AND enforces the server-wide RPM ceiling
        BEFORE sending any request to Gemini.
        """
        now = time.time()

        # 1. Per-user rapid-click guard (blocks double-clicks / button spam)
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

        # 2. Global server-wide per-minute guard (blocks multi-user bursts)
        limiter = _get_global_rate_limiter()
        with limiter["lock"]:
            now = time.time()
            while limiter["timestamps"] and now - limiter["timestamps"][0] >= 60.0:
                limiter["timestamps"].popleft()

            if len(limiter["timestamps"]) >= MAX_REQUESTS_PER_MINUTE:
                reset_in = int(60.0 - (now - limiter["timestamps"][0])) + 1
                return (
                    False,
                    f"🛑 Rate limit protection active: server quota is full for this minute. Try again in {reset_in}s.",
                )

            # Reserve slot and record user timestamp
            limiter["timestamps"].append(now)

        try:
            st.session_state["_last_ai_request_ts"] = now
        except Exception:
            pass

        return True, ""

    def _generate_with_retry(self, contents, system_instruction: str = None, max_retries: int = 2) -> str:
        """Blocks rapid requests up front, then calls Gemini with fast failover."""
        allowed, block_message = self._check_and_reserve_slot()
        if not allowed:
            return block_message

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
                        contents=contents,
                        config=config
                    )
                    return response.text or "⚠️ Empty response returned from model."
                except Exception as e:
                    last_error = str(e)
                    if any(code in last_error for code in ("503", "UNAVAILABLE", "429", "DEADLINE", "timeout")):
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return f"⚠️ AI Error: {last_error}"

        return f"⚠️ AI Error (after retries): {last_error}"

    def ask(self, prompt: str, system_instruction: str = None) -> str:
        return self._generate_with_retry(contents=prompt, system_instruction=system_instruction)

    def ask_with_image(self, prompt: str, image: Image.Image, system_instruction: str = None) -> str:
        return self._generate_with_retry(contents=[image, prompt], system_instruction=system_instruction)
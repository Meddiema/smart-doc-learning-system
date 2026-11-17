import os
import time
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types


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

    def _generate_with_retry(self, contents, system_instruction: str = None, max_retries: int = 2) -> str:
        """Call Gemini with fast failover so the UI never hangs."""
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
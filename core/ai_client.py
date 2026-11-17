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

        self.client = genai.Client(api_key=api_key)
        self.models = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

    def _generate_with_retry(self, contents, system_instruction: str = None, max_retries: int = 3) -> str:
        """Call Gemini with automatic backoff on 503/429 spikes and fallback to lighter model."""
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
                    # Retry on temporary high demand (503) or rate limit (429)
                    if "503" in last_error or "UNAVAILABLE" in last_error or "429" in last_error:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    # Non-transient error (e.g., invalid key): fail immediately
                    return f"⚠️ AI Error: {last_error}"

        return f"⚠️ AI Error (after retries): {last_error}"

    def ask(self, prompt: str, system_instruction: str = None) -> str:
        """Send a text prompt with an optional persona/system instruction."""
        return self._generate_with_retry(contents=prompt, system_instruction=system_instruction)

    def ask_with_image(self, prompt: str, image: Image.Image, system_instruction: str = None) -> str:
        """Send an image alongside a text prompt for multimodal vision analysis."""
        return self._generate_with_retry(contents=[image, prompt], system_instruction=system_instruction)
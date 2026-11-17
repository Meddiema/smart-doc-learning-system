import os
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
        self.model_name = "gemini-3.8-flash"

    def ask(self, prompt: str, system_instruction: str = None) -> str:
        """Send a text prompt with an optional persona/system instruction."""
        try:
            config = (
                types.GenerateContentConfig(system_instruction=system_instruction)
                if system_instruction
                else None
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return response.text or "⚠️ Empty response returned from model."
        except Exception as e:
            return f"⚠️ AI Error: {str(e)}"

    def ask_with_image(self, prompt: str, image: Image.Image, system_instruction: str = None) -> str:
        """Send an image alongside a text prompt for multimodal vision analysis."""
        try:
            config = (
                types.GenerateContentConfig(system_instruction=system_instruction)
                if system_instruction
                else None
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[image, prompt],
                config=config
            )
            return response.text or "⚠️ Empty response returned from vision model."
        except Exception as e:
            return f"⚠️ Vision AI Error: {str(e)}"
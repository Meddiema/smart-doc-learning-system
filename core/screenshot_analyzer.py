import os
from PIL import Image
from core.ai_client import AIClient

SCREENSHOT_DIR = os.path.join("data", "screenshots")

VISION_SYSTEM_PROMPT = """
You are a senior UI/UX engineer and system architect. Analyze the uploaded screenshot or diagram and provide:
1. **Visual & Structural Breakdown** — Key components, layout hierarchy, or data flow shown.
2. **Design & Architecture Patterns** — Patterns or best practices observed (and any potential flaws).
3. **Starter Implementation Code** — Clean, modular starter code (HTML/CSS, Streamlit, Python, or SQL depending on what the image depicts) to recreate or implement it.
"""

def save_uploaded_screenshot(uploaded_file) -> str:
    """Save an uploaded image to data/screenshots/ and return its path."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    safe_name = os.path.basename(uploaded_file.name)
    file_path = os.path.join(SCREENSHOT_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def analyze_screenshot(image_path: str, custom_prompt: str = "") -> str:
    """Open an image and analyze it with Gemini Vision."""
    ai = AIClient()
    prompt = custom_prompt.strip() or "Analyze this screenshot/diagram and generate clean starter code."
    with Image.open(image_path) as img:
        return ai.ask_with_image(prompt, img, system_instruction=VISION_SYSTEM_PROMPT)
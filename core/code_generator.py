from core.ai_client import AIClient

GENERATOR_SYSTEM_PROMPT = """
You are a senior software engineer creating runnable practice exercises.
Given a programming concept or documentation snippet, output ONLY clean, self-contained, 
runnable code with brief inline comments demonstrating the concept. 
Do not wrap the response in long prose—keep it focused on practical, testable code.
"""

class CodeGenerator:
    def __init__(self):
        self.ai = AIClient()

    def generate_starter_code(self, concept: str, language: str = "Python") -> str:
        prompt = (
            f"Target Language: {language}\n"
            f"Concept / Context:\n{concept}\n\n"
            "Write a short, runnable example I can test right now."
        )
        return self.ai.ask(prompt, system_instruction=GENERATOR_SYSTEM_PROMPT)
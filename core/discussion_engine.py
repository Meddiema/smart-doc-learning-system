import json
from core.ai_client import AIClient

PERSONAS = {
    "technical": {
        "name": "🔵 AI-1: Technical Expert",
        "system": (
            "You are a precise, senior software engineer. Explain concepts using exact technical terminology, "
            "syntax rules, edge cases, and clean code snippets. Keep it concise and accurate."
        )
    },
    "analogy": {
        "name": "🟢 AI-2: Analogy Tutor",
        "system": (
            "You are a friendly mentor who explains programming concepts using vivid real-world analogies "
            "and plain English. Avoid heavy jargon and make abstract ideas click immediately."
        )
    },
    "big_picture": {
        "name": "🟠 AI-3: System Architect",
        "system": (
            "You are a software architect focused on the big picture: why this concept exists, how it fits "
            "into larger systems, security implications, and industry best practices."
        )
    }
}


class DiscussionEngine:
    def __init__(self):
        self.ai = AIClient()

    def run_roundtable(self, topic: str, context: str = "") -> dict:
        """Runs a fast 2-call multi-AI discussion: All 3 Perspectives -> Debate + Summary."""
        # Trim context to 4,000 chars so free-tier token processing stays fast
        trimmed_context = context.strip()[:4000]
        base_prompt = f"Topic / Question: {topic}"
        if trimmed_context:
            base_prompt += f"\n\nReference Context from Document:\n{trimmed_context}"

        # Call 1: Enforces per-user cooldown + global RPM cap
        perspectives_prompt = (
            f"{base_prompt}\n\n"
            "Respond ONLY with valid JSON (no markdown fences) containing exactly these three keys:\n"
            '- "technical": Concise breakdown from AI-1 (Technical Expert) with exact syntax and a short code snippet.\n'
            '- "analogy": Plain-English explanation from AI-2 (Analogy Tutor) using a vivid real-world analogy.\n'
            '- "big_picture": Architectural view from AI-3 (System Architect) covering system design, security, and best practices.\n'
            "Keep each perspective focused and under 180 words."
        )
        raw_perspectives = self.ai.ask(
            perspectives_prompt,
            system_instruction="You simulate three distinct engineering experts. Output strictly valid JSON."
        )

        # If blocked by cooldown or rate-limit protection, return immediately without making Call 2
        if raw_perspectives.startswith(("🛑", "⚠️")):
            return {
                "technical": raw_perspectives,
                "analogy": "",
                "big_picture": "",
                "debate": "",
                "summary": ""
            }

        # Parse JSON safely with fallback if model wraps in markdown fences
        cleaned_json = raw_perspectives.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            takes = json.loads(cleaned_json)
            tech_take = takes.get("technical", raw_perspectives)
            analogy_take = takes.get("analogy", "")
            arch_take = takes.get("big_picture", "")
        except json.JSONDecodeError:
            tech_take = raw_perspectives
            analogy_take = "*(Combined into main response above)*"
            arch_take = "*(Combined into main response above)*"

        # Call 2: Bypasses per-user cooldown (part of the same action), still obeys global RPM cap
        synthesis_prompt = (
            f"Topic: {topic}\n\n"
            f"AI-1 (Technical):\n{tech_take}\n\n"
            f"AI-2 (Analogy):\n{analogy_take}\n\n"
            f"AI-3 (Architect):\n{arch_take}\n\n"
            "Respond ONLY with valid JSON (no markdown fences) containing two keys:\n"
            '- "debate": A lively 4-line roundtable exchange where AI-1, AI-2, and AI-3 directly address each other and highlight one pitfall.\n'
            '- "summary": A concise Markdown table with columns: Key Concept | Core Rule | #1 Common Mistake | Practical Takeaway.'
        )
        raw_synthesis = self.ai.ask(
            synthesis_prompt,
            system_instruction="Simulate a sharp engineering roundtable and summary table. Output strictly valid JSON.",
            bypass_user_cooldown=True
        )

        if raw_synthesis.startswith(("🛑", "⚠️")):
            return {
                "technical": tech_take,
                "analogy": analogy_take,
                "big_picture": arch_take,
                "debate": raw_synthesis,
                "summary": ""
            }

        cleaned_syn = raw_synthesis.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            syn = json.loads(cleaned_syn)
            debate = syn.get("debate", raw_synthesis)
            summary = syn.get("summary", "")
        except json.JSONDecodeError:
            debate = raw_synthesis
            summary = ""

        return {
            "technical": tech_take,
            "analogy": analogy_take,
            "big_picture": arch_take,
            "debate": debate,
            "summary": summary
        }
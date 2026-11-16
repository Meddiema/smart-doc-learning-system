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
        """Runs a 3-stage multi-AI discussion: Independent Takes -> Cross-Debate -> Final Summary."""
        base_prompt = f"Topic / Question: {topic}"
        if context.strip():
            base_prompt += f"\n\nReference Context from Document:\n{context}"

        # Stage 1: Independent Perspectives
        tech_take = self.ai.ask(
            f"{base_prompt}\n\nProvide your technical breakdown and a brief code example.",
            system_instruction=PERSONAS["technical"]["system"]
        )
        analogy_take = self.ai.ask(
            f"{base_prompt}\n\nExplain this simply with a relatable analogy.",
            system_instruction=PERSONAS["analogy"]["system"]
        )
        arch_take = self.ai.ask(
            f"{base_prompt}\n\nExplain why this matters architecturally and what best practices apply.",
            system_instruction=PERSONAS["big_picture"]["system"]
        )

        # Stage 2: Cross-Critique & Debate
        debate_prompt = (
            f"Topic: {topic}\n\n"
            f"AI-1 (Technical) said:\n{tech_take}\n\n"
            f"AI-2 (Analogy) said:\n{analogy_take}\n\n"
            f"AI-3 (Architect) said:\n{arch_take}\n\n"
            "Write a short, lively 4-line roundtable exchange where the three AIs directly address each other, "
            "point out one nuance or pitfall the others missed, and refine the explanation."
        )
        debate = self.ai.ask(
            debate_prompt,
            system_instruction="Simulate a sharp, collaborative engineering roundtable between AI-1, AI-2, and AI-3."
        )

        # Stage 3: Final Actionable Summary
        summary_prompt = (
            f"Based on the discussion below about '{topic}', create a concise Markdown summary table "
            "covering: Key Concept, Core Rule, #1 Common Mistake, and Practical Takeaway.\n\n"
            f"Discussion:\n{debate}"
        )
        summary = self.ai.ask(summary_prompt)

        return {
            "technical": tech_take,
            "analogy": analogy_take,
            "big_picture": arch_take,
            "debate": debate,
            "summary": summary
        }
import streamlit as st
from core.code_generator import CodeGenerator
from core.code_sandbox_runner import run_python_code
from core.ai_client import AIClient

LANG_MAP = {
    "python": "Python",
    "py": "Python",
    "php": "PHP",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "csharp": "C#",
    "c#": "C#",
    "cs": "C#",
    "sql": "SQL",
}


def render_try_it_sandbox():
    st.header("⚡ Interactive Try-It Sandbox")
    st.caption("Generate starter code from your reading/discussions, tweak it, and run it live.")

    # Consume one-click handoff from Document Viewer (💻 Show Code -> ⚡ Load into Try-It Sandbox)
    prefill_code = st.session_state.pop("sandbox_prefill_code", None)
    prefill_lang = st.session_state.pop("sandbox_prefill_lang", None)
    if prefill_code:
        st.session_state["sandbox_code"] = prefill_code
        st.session_state["sandbox_editor_area"] = prefill_code
        if prefill_lang:
            mapped_lang = LANG_MAP.get(prefill_lang.strip().lower(), "Python")
            st.session_state["sandbox_lang"] = mapped_lang
            st.session_state["sandbox_lang_select"] = mapped_lang
        st.session_state.pop("sandbox_output", None)
        st.session_state.pop("sandbox_review", None)
        st.toast("Code loaded from Document Viewer!")

    # Pre-fill concept from Document Viewer or AI Discussion Room if available
    default_concept = (
        st.session_state.get("discussion_topic")
        or st.session_state.get("last_highlighted_snippet")
        or ""
    )

    lang_options = ["Python", "PHP", "JavaScript", "C#", "SQL"]
    current_lang = st.session_state.get("sandbox_lang", "Python")
    lang_index = lang_options.index(current_lang) if current_lang in lang_options else 0

    with st.expander("🪄 Generate Starter Code from a Concept", expanded=not bool(st.session_state.get("sandbox_code"))):
        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            concept_input = st.text_input(
                "Concept to practice:",
                value=default_concept,
                placeholder="e.g., Python list comprehensions with filtering, or SQLite parameterized queries",
            )
        with col_c2:
            lang = st.selectbox("Language", lang_options, index=lang_index, key="sandbox_lang_select")
            st.session_state["sandbox_lang"] = lang

        if st.button("✨ Generate Practice Code"):
            if not concept_input.strip():
                st.warning("Enter a concept first.")
            else:
                with st.spinner("Generating runnable example..."):
                    gen = CodeGenerator()
                    raw_code = gen.generate_starter_code(concept_input, lang)
                    cleaned = raw_code.strip()
                    if cleaned.startswith("```"):
                        lines = cleaned.splitlines()
                        cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
                    st.session_state["sandbox_code"] = cleaned
                    st.session_state["sandbox_editor_area"] = cleaned
                    st.session_state["sandbox_lang"] = lang

    col_editor, col_console = st.columns([1.2, 1])

    with col_editor:
        st.subheader("📝 Code Editor")
        if "sandbox_editor_area" not in st.session_state:
            st.session_state["sandbox_editor_area"] = st.session_state.get(
                "sandbox_code",
                "# Write Python code here to test a concept\nprint('Hello from the Sandbox!')",
            )

        code_input = st.text_area(
            "Write or modify your code below:",
            height=340,
            key="sandbox_editor_area",
        )
        st.session_state["sandbox_code"] = code_input

        active_lang = st.session_state.get("sandbox_lang", "Python")
        is_python = active_lang == "Python"

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            run_clicked = st.button(
                "▶️ Run Python Code" if is_python else f"▶️ Run ({active_lang} — Python Runner Only)",
                type="primary",
                use_container_width=True,
                disabled=not is_python,
            )
        with btn_col2:
            explain_code_clicked = st.button("🧠 Explain My Code", use_container_width=True)

    with col_console:
        st.subheader("🖥️ Output Console")

        if run_clicked:
            with st.spinner("Running..."):
                st.session_state["sandbox_output"] = run_python_code(code_input)

        if explain_code_clicked:
            with st.spinner("Reviewing your code..."):
                ai = AIClient()
                st.session_state["sandbox_review"] = ai.ask(
                    f"Briefly explain what this {active_lang} code does line-by-line and suggest one improvement:\n\n```{active_lang.lower()}\n{code_input}\n```"
                )

        if "sandbox_output" in st.session_state:
            out = st.session_state["sandbox_output"]
            if out["success"]:
                st.success("✅ Executed Successfully")
                st.code(out["stdout"] if out["stdout"] else "(No printed output)", language="text")
            else:
                st.error("❌ Execution Error")
                st.code(out["stderr"], language="text")
                # Handoff to Error Bank
                if st.button("📉 Save This Error to Error Bank"):
                    st.session_state["prefill_error_code"] = code_input
                    st.session_state["prefill_error_msg"] = out["stderr"]
                    st.info("Error copied! Switch to **📉 Personal Error Bank** in the sidebar to analyze and save it.")

        if "sandbox_review" in st.session_state:
            st.markdown("---")
            st.markdown("**🧠 AI Code Review:**")
            st.markdown(st.session_state["sandbox_review"])
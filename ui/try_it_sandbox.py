import streamlit as st
from core.code_generator import CodeGenerator
from core.code_sandbox_runner import run_python_code
from core.ai_client import AIClient

def render_try_it_sandbox():
    st.header("⚡ Interactive Try-It Sandbox")
    st.caption("Generate starter code from your reading/discussions, tweak it, and run it live.")

    # Pre-fill concept from Document Viewer or AI Discussion Room if available
    default_concept = (
        st.session_state.get("discussion_topic")
        or st.session_state.get("last_highlighted_snippet")
        or ""
    )

    with st.expander("🪄 Generate Starter Code from a Concept", expanded=not bool(st.session_state.get("sandbox_code"))):
        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            concept_input = st.text_input(
                "Concept to practice:",
                value=default_concept,
                placeholder="e.g., Python list comprehensions with filtering, or SQLite parameterized queries"
            )
        with col_c2:
            lang = st.selectbox("Language", ["Python", "PHP", "JavaScript", "C#", "SQL"])

        if st.button("✨ Generate Practice Code"):
            if not concept_input.strip():
                st.warning("Enter a concept first.")
            else:
                with st.spinner("Generating runnable example..."):
                    gen = CodeGenerator()
                    raw_code = gen.generate_starter_code(concept_input, lang)
                    # Strip markdown code fences if present
                    cleaned = raw_code.strip()
                    if cleaned.startswith("```"):
                        lines = cleaned.splitlines()
                        cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
                    st.session_state["sandbox_code"] = cleaned
                    st.session_state["sandbox_lang"] = lang

    col_editor, col_console = st.columns([1.2, 1])

    with col_editor:
        st.subheader("📝 Code Editor")
        code_input = st.text_area(
            "Write or modify your code below:",
            value=st.session_state.get("sandbox_code", "# Write Python code here to test a concept\nprint('Hello from the Sandbox!')"),
            height=340,
            key="sandbox_editor_area"
        )
        st.session_state["sandbox_code"] = code_input

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            run_clicked = st.button("▶️ Run Python Code", type="primary", use_container_width=True)
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
                    f"Briefly explain what this code does line-by-line and suggest one improvement:\n\n```python\n{code_input}\n```"
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
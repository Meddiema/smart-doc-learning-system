import streamlit as st
from core.ai_client import AIClient
from database.error_bank_db import (
    add_error,
    get_all_errors,
    toggle_mastered,
    delete_error,
    get_error_stats
)
from ui.code_panel import render_code_panel

DIAGNOSIS_SYSTEM_PROMPT = """
You are a senior debugging mentor. Given broken code and an error message, respond in two clear sections:
1. **Root Cause (Plain English):** Why this exact error occurred.
2. **Corrected Code & Prevention Rule:** Show the fixed code and give a 1-sentence rule to avoid it next time.
"""


def render_error_bank_view():
    st.header("📉 Personal Error Bank & Debugging Mentor")

    stats = get_error_stats()
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Errors Logged", stats["total"])
    m2.metric("Needs Practice", stats["active"])
    m3.metric("Mastered", stats["mastered"])

    tab_log, tab_browse, tab_quiz = st.tabs([
        "➕ Log & Diagnose Error",
        "🔍 Search Error Bank",
        "🧠 Active Recall Quiz"
    ])

    # TAB 1: Log & Diagnose
    with tab_log:
        st.subheader("Analyze & Save a Bug")

        # Pull pre-filled values if forwarded from Try-It Sandbox
        prefill_code = st.session_state.get("prefill_error_code", "")
        prefill_msg = st.session_state.get("prefill_error_msg", "")

        col1, col2 = st.columns([2, 1])
        with col1:
            error_title = st.text_input(
                "Short Error Title / Concept",
                placeholder="e.g., ZeroDivisionError in loop or SQLite OperationalError"
            )
        with col2:
            language = st.selectbox("Language", ["Python", "PHP", "JavaScript", "C#", "SQL", "Bash"])

        broken_code = st.text_area(
            "Broken Code Snippet:",
            value=prefill_code,
            height=160,
            placeholder="Paste the code that failed..."
        )
        error_message = st.text_area(
            "Traceback / Error Output:",
            value=prefill_msg,
            height=110,
            placeholder="Paste the exact error message..."
        )

        if st.button("🩺 Diagnose & Save to Error Bank", type="primary"):
            if not broken_code.strip() or not error_message.strip():
                st.warning("Provide both the broken code and the error message.")
            else:
                with st.spinner("Diagnosing root cause and saving..."):
                    ai = AIClient()
                    prompt = f"Language: {language}\n\nBroken Code:\n{broken_code}\n\nError Message:\n{error_message}"
                    diagnosis = ai.ask(prompt, system_instruction=DIAGNOSIS_SYSTEM_PROMPT)

                    auto_title = error_title.strip() or error_message.strip().splitlines()[-1][:60]
                    add_error(
                        language=language,
                        error_title=auto_title,
                        broken_code=broken_code,
                        error_message=error_message,
                        ai_diagnosis=diagnosis
                    )
                    # Clear prefill state once saved
                    st.session_state.pop("prefill_error_code", None)
                    st.session_state.pop("prefill_error_msg", None)

                    st.success(f"Saved **{auto_title}** to your Error Bank!")
                    st.markdown(diagnosis)

    # TAB 2: Browse & Search
    with tab_browse:
        st.subheader("Your Logged Bugs & Fixes")
        f_col1, f_col2 = st.columns([3, 1])
        with f_col1:
            search_q = st.text_input("Search by keyword, error type, or language:")
        with f_col2:
            only_active = st.checkbox("Unmastered only", value=False)

        errors = get_all_errors(search_query=search_q, only_unmastered=only_active)
        if not errors:
            st.info("No matching errors found. Log an error in Tab 1 or send one from the Try-It Sandbox.")
        else:
            for err in errors:
                status_badge = "✅ Mastered" if err["mastered"] else "🟡 Practicing"
                with st.expander(f"[{err['language']}] {err['error_title']} — {status_badge}"):
                    st.caption(f"Logged on: {err['created_at']}")

                    render_code_panel(
                        err["broken_code"],
                        language=err["language"],
                        title="Broken Code",
                        allow_send_to_sandbox=True,
                        key_prefix=f"err_{err['id']}"
                    )

                    st.markdown("**Error Output:**")
                    st.code(err["error_message"], language="text")
                    st.markdown("**AI Diagnosis & Fix:**")
                    st.markdown(err["ai_diagnosis"])

                    act1, act2 = st.columns(2)
                    with act1:
                        new_state = not bool(err["mastered"])
                        btn_label = "Mark as Mastered ✅" if new_state else "Reopen for Practice 🔄"
                        if st.button(btn_label, key=f"master_{err['id']}"):
                            toggle_mastered(err["id"], new_state)
                            st.rerun()
                    with act2:
                        if st.button("Delete Entry 🗑️", key=f"del_{err['id']}"):
                            delete_error(err["id"])
                            st.rerun()

    # TAB 3: Active Recall Quiz
    with tab_quiz:
        st.subheader("Test Yourself on Past Mistakes")
        practice_pool = get_all_errors(only_unmastered=True)
        if not practice_pool:
            st.success("🎉 You have no unmastered errors left to review!")
        else:
            quiz_item = st.selectbox(
                "Pick a bug to solve from memory:",
                practice_pool,
                format_func=lambda x: f"[{x['language']}] {x['error_title']}"
            )
            st.markdown("**Spot the bug in this snippet before checking the answer:**")

            render_code_panel(
                quiz_item["broken_code"],
                language=quiz_item["language"],
                title="Quiz Snippet (Broken Code)",
                allow_send_to_sandbox=True,
                key_prefix=f"quiz_err_{quiz_item['id']}"
            )

            user_guess = st.text_input("What caused this error and how do you fix it?")
            if st.button("Reveal Solution"):
                if user_guess.strip():
                    st.info(f"**Your Answer:** {user_guess}")
                st.markdown("**Actual Error Message:**")
                st.code(quiz_item["error_message"], language="text")
                st.markdown("**Diagnosis & Solution:**")
                st.markdown(quiz_item["ai_diagnosis"])
import math
from datetime import datetime, timedelta, timezone
import streamlit as st
from core.ai_client import AIClient
from database.error_bank_db import (
    add_error,
    get_all_errors,
    toggle_mastered,
    delete_error,
    get_error_stats,
)
from ui.code_panel import render_code_panel

ERROR_RETENTION_DAYS = 15
UTC_FMT = "%Y-%m-%d %H:%M:%S"

DIAGNOSIS_SYSTEM_PROMPT = """
You are a senior debugging mentor. Given broken code and an error message, respond in two clear sections:
1. **Root Cause (Plain English):** Why this exact error occurred.
2. **Corrected Code & Prevention Rule:** Show the fixed code and give a 1-sentence rule to avoid it next time.
"""


def _parse_utc_ts(ts_str: str | None) -> datetime | None:
    if not ts_str or not isinstance(ts_str, str):
        return None
    cleaned = ts_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in (UTC_FMT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(cleaned[:26], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _error_retention_info(err: dict) -> dict:
    now_utc = datetime.now(timezone.utc)
    exp_dt = _parse_utc_ts(err.get("expires_at"))
    if exp_dt is None:
        created_dt = _parse_utc_ts(err.get("created_at"))
        if created_dt is not None:
            exp_dt = created_dt + timedelta(days=ERROR_RETENTION_DAYS)

    if exp_dt is None:
        return {
            "badge": f"⏳ {ERROR_RETENTION_DAYS}d TTL",
            "expires_label": f"{ERROR_RETENTION_DAYS}-day retention",
        }

    remaining_secs = max(0.0, (exp_dt - now_utc).total_seconds())
    hours_left = math.ceil(remaining_secs / 3600.0) if remaining_secs > 0 else 0
    days_left = math.ceil(remaining_secs / 86400.0) if remaining_secs > 0 else 0

    if remaining_secs <= 0:
        badge = "⚠️ Expiring soon"
    elif hours_left < 24:
        badge = f"⚠️ {hours_left}h left"
    else:
        badge = f"⏳ {days_left}d left"

    return {
        "badge": badge,
        "expires_label": exp_dt.strftime("%b %d, %H:%M UTC"),
    }


def _render_solution_and_fix(err: dict, key_suffix: str):
    """Render error output, fixed_code (if present), and AI diagnosis."""
    st.markdown("**Error Output:**")
    st.code(err["error_message"], language="text")

    fixed_code = (err.get("fixed_code") or "").strip()
    if fixed_code:
        render_code_panel(
            fixed_code,
            language=err["language"],
            title="Expected Fix / Command",
            allow_send_to_sandbox=True,
            key_prefix=f"fix_{err['id']}_{key_suffix}",
        )

    st.markdown("**AI Diagnosis & Fix:**")
    st.markdown(err["ai_diagnosis"])


def render_error_bank_view():
    st.header("📉 Personal Error Bank & Debugging Mentor")
    st.caption("Logged bugs stay in your Error Bank for **15 days** so you can drill weak spots before they auto-expire.")

    stats = get_error_stats()
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Errors Logged", stats["total"])
    m2.metric("Needs Practice", stats["active"])
    m3.metric("Mastered", stats["mastered"])

    tab_log, tab_browse, tab_quiz = st.tabs([
        "➕ Log & Diagnose Error",
        "🔍 Search Error Bank",
        "🧠 Active Recall Quiz",
    ])

    # TAB 1: Log & Diagnose
    with tab_log:
        st.subheader("Analyze & Save a Bug")

        prefill_code = st.session_state.get("prefill_error_code", "")
        prefill_msg = st.session_state.get("prefill_error_msg", "")

        col1, col2 = st.columns([2, 1])
        with col1:
            error_title = st.text_input(
                "Short Error Title / Concept",
                placeholder="e.g., ZeroDivisionError in loop or SQLite OperationalError",
                key="eb_title_input",
            )
        with col2:
            language = st.selectbox(
                "Language",
                ["Python", "PHP", "JavaScript", "C#", "SQL", "Bash"],
                key="eb_lang_select",
            )

        broken_code = st.text_area(
            "Broken Code Snippet:",
            value=prefill_code,
            height=160,
            placeholder="Paste the code that failed...",
            key="eb_broken_code_input",
        )
        error_message = st.text_area(
            "Traceback / Error Output:",
            value=prefill_msg,
            height=110,
            placeholder="Paste the exact error message...",
            key="eb_error_msg_input",
        )

        if st.button("🩺 Diagnose & Save to Error Bank", type="primary", key="eb_diagnose_btn"):
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
                        ai_diagnosis=diagnosis,
                    )
                    st.session_state.pop("prefill_error_code", None)
                    st.session_state.pop("prefill_error_msg", None)

                    st.success(f"Saved **{auto_title}** to your Error Bank (15-day retention)!")
                    st.markdown(diagnosis)

    # TAB 2: Browse & Search
    with tab_browse:
        st.subheader("Your Logged Bugs & Fixes")
        f_col1, f_col2, f_col3 = st.columns([2.6, 1.1, 1.3])
        with f_col1:
            search_q = st.text_input(
                "Search by keyword, error type, or language:",
                key="eb_search_q",
            )
        with f_col2:
            st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
            drill_mode = st.toggle(
                "🎯 Drill Unmastered Errors",
                value=False,
                key="eb_drill_mode",
                help="Focus on unmastered bugs and hide AI diagnosis & fixed code behind an expander until you try solving from memory.",
            )
        with f_col3:
            st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
            only_active = st.checkbox(
                "Unmastered only",
                value=drill_mode,
                disabled=drill_mode,
                key="eb_only_active",
            )

        effective_unmastered = bool(only_active or drill_mode)
        if drill_mode:
            st.info("🎯 **Drill Mode Active:** Attempt the fix or command from memory first, then expand **Reveal Solution & Fixed Code**.")

        errors = get_all_errors(search_query=search_q, only_unmastered=effective_unmastered)
        if not errors:
            st.info("No matching errors found. Log an error in Tab 1 or send one from the Try-It Sandbox.")
        else:
            for err in errors:
                status_badge = "✅ Mastered" if err["mastered"] else "🟡 Practicing"
                ret = _error_retention_info(err)
                expander_label = (
                    f"[{err['language']}] {err['error_title']} — {status_badge} • {ret['badge']}"
                )
                with st.expander(expander_label):
                    st.caption(f"Logged on: {err['created_at']} • {ret['badge']} (expires {ret['expires_label']})")

                    render_code_panel(
                        err["broken_code"],
                        language=err["language"],
                        title="Broken Code",
                        allow_send_to_sandbox=True,
                        key_prefix=f"err_{err['id']}",
                    )

                    if drill_mode and not err["mastered"]:
                        st.text_input(
                            "Your attempt (fix or command from memory):",
                            key=f"drill_attempt_{err['id']}",
                            placeholder="Write your fix or CLI flag before revealing...",
                        )
                        with st.expander("🔍 Reveal Solution & Fixed Code"):
                            _render_solution_and_fix(err, key_suffix="drill")
                    else:
                        _render_solution_and_fix(err, key_suffix="browse")

                    act1, act2 = st.columns(2)
                    with act1:
                        new_state = not bool(err["mastered"])
                        btn_label = "Mark as Mastered ✅" if new_state else "Reopen for Practice 🔄"
                        if st.button(btn_label, key=f"master_{err['id']}", use_container_width=True):
                            toggle_mastered(err["id"], new_state)
                            st.rerun()
                    with act2:
                        if st.button("Delete Entry 🗑️", key=f"del_{err['id']}", use_container_width=True):
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
                format_func=lambda x: f"[{x['language']}] {x['error_title']} • {_error_retention_info(x)['badge']}",
                key="eb_quiz_select",
            )
            ret = _error_retention_info(quiz_item)
            st.caption(f"Retention: {ret['badge']} (expires {ret['expires_label']})")
            st.markdown("**Spot the bug in this snippet before checking the answer:**")

            render_code_panel(
                quiz_item["broken_code"],
                language=quiz_item["language"],
                title="Quiz Snippet (Broken Code)",
                allow_send_to_sandbox=True,
                key_prefix=f"quiz_err_{quiz_item['id']}",
            )

            reveal_key = f"eb_reveal_{quiz_item['id']}"
            user_guess = st.text_input(
                "What caused this error and how do you fix it?",
                key=f"eb_guess_{quiz_item['id']}",
            )
            if st.button("Reveal Solution", key=f"eb_reveal_btn_{quiz_item['id']}"):
                st.session_state[reveal_key] = True

            if st.session_state.get(reveal_key):
                if user_guess.strip():
                    st.info(f"**Your Attempt:** {user_guess}")
                _render_solution_and_fix(quiz_item, key_suffix="quiz")

                if st.button("Mark Bug as Mastered ✅", key=f"eb_quiz_master_{quiz_item['id']}"):
                    toggle_mastered(quiz_item["id"], True)
                    st.session_state.pop(reveal_key, None)
                    st.toast("Marked as Mastered!")
                    st.rerun()
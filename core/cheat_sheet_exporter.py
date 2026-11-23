from datetime import datetime
import streamlit as st


def record_study_note(
    source: str,
    title: str,
    explanation: str = "",
    code: str = "",
    code_lang: str = "python",
    command: str = "",
    command_notes: str = "",
):
    """Append a translated concept, command, or summary to the active session cheat-sheet."""
    notes = st.session_state.setdefault("study_session_notes", [])
    clean_title = (title or "Untitled Concept").strip()

    entry = {
        "timestamp": datetime.now().strftime("%H:%M"),
        "source": source,
        "title": clean_title,
        "explanation": explanation,
        "code": code,
        "code_lang": code_lang or "python",
        "command": command,
        "command_notes": command_notes,
    }

    # Update in place if the same concept from the same source is regenerated on rerun
    if notes and notes[-1].get("title") == clean_title and notes[-1].get("source") == source:
        notes[-1] = entry
        return

    notes.append(entry)


def build_markdown_cheat_sheet() -> str:
    """Compile all active session notes, code, CLI commands, and quizzes into a .md guide."""
    notes = st.session_state.get("study_session_notes", [])
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 📘 Smart Study Cheat-Sheet",
        f"**Generated:** {date_str} | **Total Captured Concepts:** {len(notes)}",
        "",
        "---",
        "",
    ]

    if not notes:
        lines.append("_No concepts captured yet in this session. Translate a snippet or run a quiz first!_")
        return "\n".join(lines)

    for idx, item in enumerate(notes, start=1):
        lines.append(f"## {idx}. {item['title']}")
        lines.append(f"*Source: {item['source']} • Captured at {item['timestamp']}*")
        lines.append("")

        if item.get("explanation"):
            lines.append("### 🔤 Explanation & Key Takeaways")
            lines.append(item["explanation"].strip())
            lines.append("")

        code_text = (item.get("code") or "").strip()
        if code_text and not code_text.startswith("# No code snippet") and not code_text.startswith("# Switch to Explain"):
            lang = item.get("code_lang", "python")
            lines.append(f"### 💻 Code Implementation ({lang})")
            lines.append(f"```{lang}")
            lines.append(code_text)
            lines.append("```")
            lines.append("")

        cmd_text = (item.get("command") or "").strip()
        if cmd_text and not cmd_text.startswith("# No terminal command") and not cmd_text.startswith("# Switch to Explain"):
            lines.append("### ⌨️ CLI / Terminal Commands")
            lines.append("```bash")
            lines.append(cmd_text)
            lines.append("```")
            if item.get("command_notes"):
                lines.append(item["command_notes"].strip())
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def render_cheat_sheet_download(location_key: str = "doc_viewer"):
    """Render a zero-API-cost Markdown cheat-sheet download button."""
    notes = st.session_state.get("study_session_notes", [])
    count = len(notes)

    if count == 0:
        st.caption("📥 Translate concepts or take a quiz to build your downloadable `.md` cheat-sheet.")
        return

    md_content = build_markdown_cheat_sheet()
    filename = f"study_cheatsheet_{datetime.now().strftime('%Y%m%d_%H%M')}.md"

    col_info, col_btn = st.columns([2.2, 1])
    with col_info:
        st.caption(f"📚 **{count}** concept(s) ready in your session cheat-sheet (zero API cost).")
    with col_btn:
        st.download_button(
            label="📥 Download .md Cheat-Sheet",
            data=md_content.encode("utf-8"),
            file_name=filename,
            mime="text/markdown",
            use_container_width=True,
            key=f"dl_cheatsheet_{location_key}",
        )
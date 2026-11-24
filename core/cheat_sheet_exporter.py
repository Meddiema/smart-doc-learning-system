import re
from datetime import datetime
import streamlit as st


def _safe_key(raw_key: str) -> str:
    """Normalize widget keys so special characters or spaces never cause Streamlit key errors."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (raw_key or "default").strip())
    return cleaned or "default"


def _get_session_notes() -> list[dict]:
    """Safely retrieve or initialize the list of captured study notes in session state."""
    try:
        notes = st.session_state.get("study_session_notes")
        if not isinstance(notes, list):
            notes = []
            st.session_state["study_session_notes"] = notes
        return notes
    except Exception:
        return []


def record_study_note(
    source: str,
    title: str,
    explanation: str = "",
    code: str = "",
    code_lang: str = "python",
    command: str = "",
    command_notes: str = "",
) -> None:
    """Add or deduplicate a translated concept, command, or summary in the active session cheat-sheet."""
    notes = _get_session_notes()
    clean_source = str(source or "Study Session").strip() or "Study Session"
    clean_title = str(title or "Untitled Concept").strip() or "Untitled Concept"
    clean_lang = str(code_lang or "python").strip() or "python"

    entry = {
        "timestamp": datetime.now().strftime("%H:%M"),
        "source": clean_source,
        "title": clean_title,
        "explanation": str(explanation or ""),
        "code": str(code or ""),
        "code_lang": clean_lang,
        "command": str(command or ""),
        "command_notes": str(command_notes or ""),
    }

    match_key = (clean_source.lower(), clean_title.lower())

    # Deduplicate by (source, title) across the session: update in place and bring to latest order
    for idx, existing in enumerate(notes):
        if not isinstance(existing, dict):
            continue
        existing_key = (
            str(existing.get("source") or "").strip().lower(),
            str(existing.get("title") or "").strip().lower(),
        )
        if existing_key == match_key:
            notes.pop(idx)
            notes.append(entry)
            return

    notes.append(entry)


def build_markdown_cheat_sheet() -> str:
    """Compile all active session notes, code, CLI commands, and quizzes into a .md guide."""
    notes = _get_session_notes()
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
        if not isinstance(item, dict):
            continue

        item_title = str(item.get("title") or "Untitled Concept").strip()
        item_source = str(item.get("source") or "Study Session").strip()
        item_time = str(item.get("timestamp") or "").strip()

        lines.append(f"## {idx}. {item_title}")
        if item_time:
            lines.append(f"*Source: {item_source} • Captured at {item_time}*")
        else:
            lines.append(f"*Source: {item_source}*")
        lines.append("")

        explanation_text = str(item.get("explanation") or "").strip()
        if explanation_text:
            lines.append("### 🔤 Explanation & Key Takeaways")
            lines.append(explanation_text)
            lines.append("")

        code_text = str(item.get("code") or "").strip()
        if (
            code_text
            and not code_text.startswith("# No code snippet")
            and not code_text.startswith("# Switch to Explain")
        ):
            lang = str(item.get("code_lang") or "python").strip() or "python"
            lines.append(f"### 💻 Code Implementation ({lang})")
            lines.append(f"```{lang}")
            lines.append(code_text)
            lines.append("```")
            lines.append("")

        cmd_text = str(item.get("command") or "").strip()
        if (
            cmd_text
            and not cmd_text.startswith("# No terminal command")
            and not cmd_text.startswith("# Switch to Explain")
        ):
            lines.append("### ⌨️ CLI / Terminal Commands")
            lines.append("```bash")
            lines.append(cmd_text)
            lines.append("```")
            cmd_notes = str(item.get("command_notes") or "").strip()
            if cmd_notes:
                lines.append(cmd_notes)
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def render_cheat_sheet_download(location_key: str = "doc_viewer") -> None:
    """Render a zero-API-cost Markdown cheat-sheet download button with a live note counter."""
    try:
        notes = _get_session_notes()
        count = len(notes)

        if count == 0:
            st.caption("📥 Translate concepts or take a quiz to build your downloadable `.md` cheat-sheet.")
            return

        note_word = "note" if count == 1 else "notes"
        md_content = build_markdown_cheat_sheet()
        filename = f"study_cheatsheet_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        button_label = f"📥 Download Cheat-Sheet ({count} {note_word})"
        safe_widget_key = f"dl_cheatsheet_{_safe_key(location_key)}"

        if location_key == "sidebar":
            st.caption(f"📚 **{count}** unique {note_word} ready (zero API cost).")
            st.download_button(
                label=button_label,
                data=md_content.encode("utf-8"),
                file_name=filename,
                mime="text/markdown",
                use_container_width=True,
                key=safe_widget_key,
            )
        else:
            col_info, col_btn = st.columns([2.0, 1.2])
            with col_info:
                st.caption(f"📚 **{count}** unique {note_word} ready in your session cheat-sheet (zero API cost).")
            with col_btn:
                st.download_button(
                    label=button_label,
                    data=md_content.encode("utf-8"),
                    file_name=filename,
                    mime="text/markdown",
                    use_container_width=True,
                    key=safe_widget_key,
                )
    except Exception as exc:
        st.caption(f"⚠️ Cheat-sheet download temporarily unavailable: {exc}")
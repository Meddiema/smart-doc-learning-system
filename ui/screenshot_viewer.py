import os
import re
import streamlit as st
from core.screenshot_analyzer import save_uploaded_screenshot, analyze_screenshot
from core.cheat_sheet_exporter import record_study_note, render_cheat_sheet_download
from database.documents_db import get_document_days_remaining
from database.screenshots_db import (
    save_screenshot_record,
    get_all_screenshots,
    delete_screenshot_record,
)
from ui.code_panel import render_code_panel

CODE_BLOCK_PATTERN = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)


def _extract_code_blocks(markdown_text: str) -> list[tuple[str, str]]:
    """Extract (language, code) pairs from fenced Markdown code blocks."""
    matches = CODE_BLOCK_PATTERN.findall(markdown_text or "")
    return [(lang.strip() or "python", code.strip()) for lang, code in matches if code.strip()]


def _strip_code_blocks(markdown_text: str) -> str:
    """Remove fenced code blocks so prose analysis renders cleanly without duplicate code."""
    cleaned = CODE_BLOCK_PATTERN.sub("", markdown_text or "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


@st.cache_data(ttl=120, show_spinner=False)
def _cached_get_all_screenshots():
    """Cache Turso screenshot history for 2 minutes so mode toggles don't re-query DB."""
    return get_all_screenshots()


def _render_vision_output(vision_output: str, view_mode: str, key_prefix: str):
    """Render analysis prose, extracted code panels, or both based on the active toggle."""
    analysis_prose = _strip_code_blocks(vision_output)
    code_blocks = _extract_code_blocks(vision_output)

    if view_mode in ("📋 Both", "🔍 Analysis Only"):
        if analysis_prose:
            st.markdown(analysis_prose)
        else:
            st.info("No narrative analysis text was returned for this screenshot.")

    if view_mode in ("📋 Both", "💻 Code Only"):
        if code_blocks:
            for idx, (lang, snippet) in enumerate(code_blocks, start=1):
                render_code_panel(
                    code=snippet,
                    language=lang,
                    title=f"Extracted Starter Code #{idx}",
                    key_prefix=f"{key_prefix}_{idx}",
                )
        else:
            st.info("No runnable code blocks were detected in this response.")


@st.fragment
def _render_active_analyzer(saved_path: str):
    col_img, col_ctrl = st.columns([1, 1.2])

    with col_img:
        st.image(saved_path, caption=os.path.basename(saved_path), use_container_width=True)

    with col_ctrl:
        focus_prompt = st.text_area(
            "What should the AI focus on?",
            placeholder="e.g., Convert this wireframe into a clean Streamlit layout, or explain this network topology...",
            height=120,
            key="vision_focus_prompt",
        )

        # Guides the prompt intent while still allowing instant switching afterward
        target_mode = st.radio(
            "Output Mode:",
            ["📋 Both", "🔍 Analysis Only", "💻 Code Only"],
            horizontal=True,
            key="vision_output_mode",
        )

        button_labels = {
            "📋 Both": "🔍 Analyze Image & Generate Code",
            "🔍 Analysis Only": "🔍 Analyze Image Architecture / Error",
            "💻 Code Only": "💻 Generate Starter Code from Image",
        }

        if st.button(button_labels[target_mode], type="primary", use_container_width=True):
            with st.spinner("Analyzing visual structure..."):
                mode_hint = ""
                if target_mode == "🔍 Analysis Only":
                    mode_hint = "\n\nFocus primarily on a thorough visual/architectural/error analysis."
                elif target_mode == "💻 Code Only":
                    mode_hint = "\n\nFocus primarily on generating clean, complete, runnable code implementing this visual."

                result = analyze_screenshot(saved_path, f"{focus_prompt}{mode_hint}".strip())
                extracted_blocks = _extract_code_blocks(result)
                first_lang = extracted_blocks[0][0] if extracted_blocks else "python"
                first_code = extracted_blocks[0][1] if extracted_blocks else ""
                analysis_prose = _strip_code_blocks(result)

                filename = os.path.basename(saved_path)
                save_screenshot_record(
                    filename=filename,
                    analysis=result,
                    starter_code=first_code,
                )
                _cached_get_all_screenshots.clear()
                st.session_state["last_vision_result"] = result

                # Automatically record visual analysis + extracted code to the offline cheat-sheet
                note_title = focus_prompt.strip().splitlines()[0][:65] if focus_prompt.strip() else filename
                record_study_note(
                    source=f"Screenshot Analyzer ({filename})",
                    title=note_title,
                    explanation=analysis_prose,
                    code=first_code,
                    code_lang=first_lang,
                )

    if "last_vision_result" in st.session_state:
        vision_output = st.session_state["last_vision_result"]
        st.markdown("---")

        active_view = st.session_state.get("vision_output_mode", "📋 Both")
        _render_vision_output(
            vision_output=vision_output,
            view_mode=active_view,
            key_prefix="vision_snippet",
        )

        extracted_blocks = _extract_code_blocks(vision_output)
        if st.button("⚡ Load into Try-It Sandbox", use_container_width=True):
            st.session_state["last_highlighted_snippet"] = vision_output
            if extracted_blocks:
                st.session_state["sandbox_prefill_lang"] = extracted_blocks[0][0]
                st.session_state["sandbox_prefill_code"] = extracted_blocks[0][1]
            st.info("Code & context loaded! Open **⚡ Interactive Try-It Sandbox** in the sidebar to run or modify it.")


def render_screenshot_viewer():
    st.header("🖼️ Screenshot & Architecture Analyzer")
    st.caption(
        "Upload UI mockups, system architecture diagrams, or error screenshots to extract insights and starter code. "
        "Saved analyses auto-expire after **7 days** or can be deleted anytime."
    )

    uploaded_img = st.file_uploader(
        "Upload a screenshot or diagram (PNG, JPG, WEBP)",
        type=["png", "jpg", "jpeg", "webp"],
    )

    if uploaded_img is not None:
        saved_path = save_uploaded_screenshot(uploaded_img)
        _render_active_analyzer(saved_path)

    st.markdown("---")
    render_cheat_sheet_download(location_key="screenshot_viewer")

    st.markdown("---")
    st.subheader("🗂️ Past Visual Analyses")
    history = _cached_get_all_screenshots()
    if not history:
        st.info("No screenshots analyzed yet.")
    else:
        history_view = st.radio(
            "History Display Filter:",
            ["📋 Both", "🔍 Analysis Only", "💻 Code Only"],
            horizontal=True,
            key="vision_history_mode",
        )
        for item in history:
            retention = get_document_days_remaining(
                expires_at=item.get("expires_at"),
                uploaded_at=item.get("created_at"),
                retention_days=7,
            )
            expander_title = (
                f"🖼️ {item['filename']} • {retention['badge']} "
                f"(expires {retention['expires_label']})"
            )
            with st.expander(expander_title):
                _render_vision_output(
                    vision_output=item["analysis"],
                    view_mode=history_view,
                    key_prefix=f"history_{item['id']}",
                )

                col_del, _ = st.columns([1.2, 3.8])
                with col_del:
                    if st.button("🗑️ Delete Analysis", key=f"del_shot_{item['id']}", use_container_width=True):
                        delete_screenshot_record(
                            screenshot_id=item["id"],
                            filename=item.get("filename", ""),
                        )
                        _cached_get_all_screenshots.clear()
                        st.toast(f"Deleted {item['filename']}")
                        st.rerun()
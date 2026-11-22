import os
import re
import streamlit as st
from core.screenshot_analyzer import save_uploaded_screenshot, analyze_screenshot
from database.screenshots_db import save_screenshot_record, get_all_screenshots
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
                first_code = extracted_blocks[0][1] if extracted_blocks else ""

                save_screenshot_record(
                    filename=os.path.basename(saved_path),
                    analysis=result,
                    starter_code=first_code,
                )
                _cached_get_all_screenshots.clear()
                st.session_state["last_vision_result"] = result

    if "last_vision_result" in st.session_state:
        vision_output = st.session_state["last_vision_result"]
        st.markdown("---")

        active_view = st.session_state.get("vision_output_mode", "📋 Both")
        _render_vision_output(
            vision_output=vision_output,
            view_mode=active_view,
            key_prefix="vision_snippet",
        )

        if st.button("⚡ Send Full Analysis Context to Try-It Sandbox"):
            st.session_state["last_highlighted_snippet"] = vision_output
            st.info("Context copied! Open **⚡ Interactive Try-It Sandbox** in the sidebar to generate and test code.")


def render_screenshot_viewer():
    st.header("🖼️ Screenshot & Architecture Analyzer")
    st.caption("Upload UI mockups, system architecture diagrams, or error screenshots to extract insights and starter code.")

    uploaded_img = st.file_uploader(
        "Upload a screenshot or diagram (PNG, JPG, WEBP)",
        type=["png", "jpg", "jpeg", "webp"],
    )

    if uploaded_img is not None:
        saved_path = save_uploaded_screenshot(uploaded_img)
        _render_active_analyzer(saved_path)

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
            with st.expander(f"🖼️ {item['filename']} ({item['created_at']})"):
                _render_vision_output(
                    vision_output=item["analysis"],
                    view_mode=history_view,
                    key_prefix=f"history_{item['id']}",
                )
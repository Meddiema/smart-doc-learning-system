import os
import re
import streamlit as st
from core.screenshot_analyzer import save_uploaded_screenshot, analyze_screenshot
from database.screenshots_db import save_screenshot_record, get_all_screenshots
from ui.code_panel import render_code_panel


def _extract_code_blocks(markdown_text: str) -> list[tuple[str, str]]:
    """Extract (language, code) pairs from fenced Markdown code blocks."""
    pattern = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
    matches = pattern.findall(markdown_text or "")
    return [(lang.strip() or "python", code.strip()) for lang, code in matches if code.strip()]


def render_screenshot_viewer():
    st.header("🖼️ Screenshot & Architecture Analyzer")
    st.caption("Upload UI mockups, system architecture diagrams, or error screenshots to extract insights and starter code.")

    uploaded_img = st.file_uploader(
        "Upload a screenshot or diagram (PNG, JPG, WEBP)",
        type=["png", "jpg", "jpeg", "webp"]
    )

    if uploaded_img is not None:
        saved_path = save_uploaded_screenshot(uploaded_img)
        col_img, col_ctrl = st.columns([1, 1.2])

        with col_img:
            st.image(saved_path, caption=os.path.basename(saved_path), use_container_width=True)

        with col_ctrl:
            focus_prompt = st.text_area(
                "What should the AI focus on?",
                placeholder="e.g., Convert this wireframe into a clean Streamlit layout, or explain this network topology...",
                height=120
            )
            if st.button("🔍 Analyze Image & Generate Code", type="primary", use_container_width=True):
                with st.spinner("Analyzing visual structure..."):
                    result = analyze_screenshot(saved_path, focus_prompt)
                    extracted_blocks = _extract_code_blocks(result)
                    first_code = extracted_blocks[0][1] if extracted_blocks else ""

                    save_screenshot_record(
                        filename=os.path.basename(saved_path),
                        analysis=result,
                        starter_code=first_code
                    )
                    st.session_state["last_vision_result"] = result

        if "last_vision_result" in st.session_state:
            vision_output = st.session_state["last_vision_result"]
            st.markdown("---")
            st.markdown(vision_output)

            # Render interactive code panels for any extracted code snippets
            code_blocks = _extract_code_blocks(vision_output)
            for idx, (lang, snippet) in enumerate(code_blocks, start=1):
                render_code_panel(
                    code=snippet,
                    language=lang,
                    title=f"Extracted Starter Code #{idx}",
                    key_prefix=f"vision_snippet_{idx}"
                )

            if st.button("⚡ Send Full Analysis Context to Try-It Sandbox"):
                st.session_state["last_highlighted_snippet"] = vision_output
                st.info("Context copied! Open **⚡ Interactive Try-It Sandbox** in the sidebar to generate and test code.")

    st.markdown("---")
    st.subheader("🗂️ Past Visual Analyses")
    history = get_all_screenshots()
    if not history:
        st.info("No screenshots analyzed yet.")
    else:
        for item in history:
            with st.expander(f"🖼️ {item['filename']} ({item['created_at']})"):
                st.markdown(item["analysis"])
                saved_blocks = _extract_code_blocks(item["analysis"])
                for idx, (lang, snippet) in enumerate(saved_blocks, start=1):
                    render_code_panel(
                        code=snippet,
                        language=lang,
                        title=f"Saved Snippet #{idx}",
                        key_prefix=f"history_{item['id']}_{idx}"
                    )
import streamlit as st
from core.ai_client import AIClient
from core.cheat_sheet_exporter import record_study_note
from core.range_synthesizer import (
    RANGE_SYNTHESIS_SYSTEM_PROMPT,
    build_page_window_digest,
    format_range_synthesis_markdown,
)


def render_range_synthesis_panel(
    pages_input,
    doc_title: str = "Document",
    total_pages: int | None = None,
    key_prefix: str = "doc_range_synth",
) -> None:
    """Render UI to synthesize flow, meaning, and industry use across a page range (e.g., 1..100)."""
    st.subheader("🧭 Multi-Page Flow & Industry Synthesis")
    st.caption(
        "Connect the moving parts across a range of pages you read (for example, pages 1–100), understand what they mean together, and see how to apply them in industry."
    )

    max_p = int(total_pages) if (total_pages and total_pages > 0) else 100
    if isinstance(pages_input, dict) and pages_input:
        numeric_keys = [int(k) for k in pages_input.keys() if str(k).isdigit()]
        if numeric_keys:
            max_p = max(max_p, max(numeric_keys))
    elif isinstance(pages_input, (list, tuple)) and len(pages_input) > 0:
        max_p = max(max_p, len(pages_input))

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        start_page = st.number_input(
            "Start Page",
            min_value=1,
            max_value=max(1, max_p),
            value=1,
            step=1,
            key=f"{key_prefix}_start",
        )
    with c2:
        default_end = min(max_p, 100) if max_p >= 10 else max_p
        end_page = st.number_input(
            "End Page",
            min_value=1,
            max_value=max(1, max_p),
            value=max(1, default_end),
            step=1,
            key=f"{key_prefix}_end",
        )
    with c3:
        focus_topic = st.text_input(
            "Optional Focus / Role Lens:",
            placeholder="e.g., backend architecture, threat modeling, Linux/cloud ops",
            key=f"{key_prefix}_focus",
        )

    state_key = f"{key_prefix}_result_{doc_title}"

    if st.button(
        f"🔗 Synthesize Pages {int(start_page)}–{int(end_page)} for Industry Work",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_run_btn",
    ):
        digest = build_page_window_digest(pages_input, int(start_page), int(end_page))
        if not digest["digest_text"]:
            st.warning("No readable text found in that page range. Check the page numbers or document text extraction.")
            return

        with st.spinner(
            f"Tracing connections across pages {digest['actual_start']}–{digest['actual_end']}..."
        ):
            ai = AIClient()
            focus_part = f"Focus Lens: {focus_topic.strip()}\n" if focus_topic.strip() else ""
            prompt = (
                f"Document: {doc_title}\n"
                f"Requested Page Range: {int(start_page)} to {int(end_page)} "
                f"(Pages in range: {digest['selected_count']}, Excerpts sampled: {digest['sampled_count']})\n"
                f"{focus_part}\n"
                f"Extracted Page Excerpts:\n{digest['digest_text']}"
            )
            ai_output = ai.ask(prompt, system_instruction=RANGE_SYNTHESIS_SYSTEM_PROMPT)
            formatted_md = format_range_synthesis_markdown(
                doc_title=doc_title,
                start_page=int(start_page),
                end_page=int(end_page),
                focus_topic=focus_topic,
                synthesis_body=ai_output,
            )
            st.session_state[state_key] = {
                "markdown": formatted_md,
                "meta": digest,
            }
            record_study_note(
                source="Page Range Synthesizer",
                title=f"{doc_title} (Pages {int(start_page)}–{int(end_page)})",
                explanation=formatted_md,
                command_notes="Synthesized page-to-page flow, core meaning, and industry application.",
            )
            st.toast("Saved page-range synthesis to your session cheat-sheet!")

    saved = st.session_state.get(state_key)
    if saved and isinstance(saved, dict):
        meta = saved.get("meta", {})
        if meta:
            st.caption(
                f"Analyzed pages **{meta.get('actual_start')}–{meta.get('actual_end')}** "
                f"({meta.get('sampled_count')} excerpts sampled across {meta.get('selected_count')} pages in range)."
            )
        st.markdown(saved.get("markdown", ""))
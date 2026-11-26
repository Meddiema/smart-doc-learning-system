import streamlit as st
from core.ai_client import AIClient
from core.cheat_sheet_exporter import record_study_note
from core.range_synthesizer import (
    BATCH_PUZZLE_EXTRACTION_PROMPT,
    MASTER_PUZZLE_ASSEMBLY_PROMPT,
    RANGE_SYNTHESIS_SYSTEM_PROMPT,
    build_page_window_digest,
    build_sequential_batches,
    format_range_synthesis_markdown,
)


def render_range_synthesis_panel(
    pages_input,
    doc_title: str = "Document",
    total_pages: int | None = None,
    key_prefix: str = "doc_range_synth",
) -> None:
    """Render UI to assemble puzzle pieces across a page range (e.g., 1..100) into one clear mental model."""
    st.subheader("🧭 Multi-Page Puzzle & Industry Synthesis")
    st.caption(
        "Connect the small puzzle pieces across a range of pages you read (for example, pages 1–100) "
        "into one unified explanation and see how to use it in industry work."
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
            "Anchor Question or Role Lens (Optional):",
            placeholder="e.g., How do tokens, sessions, and CSRF defenses fit together?",
            key=f"{key_prefix}_focus",
        )

    depth_mode = st.radio(
        "Synthesis Depth:",
        [
            "🧠 Deep Multi-Pass (Reads every batch in sequence — best for connecting 1–100 pages)",
            "⚡ Fast Overview (Single sampled pass — quickest check)",
        ],
        horizontal=True,
        key=f"{key_prefix}_depth_mode",
    )
    is_deep_mode = depth_mode.startswith("🧠")

    state_key = f"{key_prefix}_result_{doc_title}"

    if st.button(
        f"🧩 Connect Pages {int(start_page)}–{int(end_page)} into One Clear Picture",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_run_btn",
    ):
        ai = AIClient()
        focus_part = f"Anchor Question / Focus Lens: {focus_topic.strip()}\n" if focus_topic.strip() else ""

        if is_deep_mode:
            batch_plan = build_sequential_batches(
                pages_input,
                int(start_page),
                int(end_page),
                batch_size=20,
            )
            batches = batch_plan["batches"]
            if not batches:
                st.warning("No readable text found in that page range. Check the page numbers or document text extraction.")
                return

            progress_bar = st.progress(0, text="Starting sequential puzzle-piece extraction...")
            ledgers = []
            total_steps = len(batches) + 1

            for idx, batch in enumerate(batches, start=1):
                progress_bar.progress(
                    int(((idx - 1) / total_steps) * 100),
                    text=f"Step {idx}/{total_steps}: Extracting puzzle pieces from pages {batch['start_page']}–{batch['end_page']}...",
                )
                batch_prompt = (
                    f"Document: {doc_title}\n"
                    f"Batch {idx} of {len(batches)} (Pages {batch['start_page']}–{batch['end_page']})\n"
                    f"{focus_part}\n"
                    f"Page Text:\n{batch['digest_text']}"
                )
                ledger_text = ai.ask(batch_prompt, system_instruction=BATCH_PUZZLE_EXTRACTION_PROMPT)
                ledgers.append(
                    {
                        "span": f"Pages {batch['start_page']}–{batch['end_page']}",
                        "ledger": ledger_text.strip(),
                    }
                )

            progress_bar.progress(
                int((len(batches) / total_steps) * 100),
                text=f"Step {total_steps}/{total_steps}: Assembling all puzzle pieces across pages {batch_plan['actual_start']}–{batch_plan['actual_end']}...",
            )

            combined_ledgers_text = "\n\n".join(
                f"### [{item['span']}]\n{item['ledger']}" for item in ledgers
            )
            master_prompt = (
                f"Document: {doc_title}\n"
                f"Full Selected Span: Pages {batch_plan['actual_start']}–{batch_plan['actual_end']} "
                f"({batch_plan['selected_count']} pages analyzed across {len(batches)} sequential batches)\n"
                f"{focus_part}\n"
                f"Sequential Puzzle-Piece Ledgers:\n{combined_ledgers_text}"
            )
            ai_output = ai.ask(master_prompt, system_instruction=MASTER_PUZZLE_ASSEMBLY_PROMPT)
            progress_bar.progress(100, text="Puzzle assembly complete!")
            progress_bar.empty()

            formatted_md = format_range_synthesis_markdown(
                doc_title=doc_title,
                start_page=int(start_page),
                end_page=int(end_page),
                focus_topic=focus_topic,
                synthesis_body=ai_output,
                mode_label=f"Deep Multi-Pass • {len(batches)} sequential batches",
            )
            st.session_state[state_key] = {
                "markdown": formatted_md,
                "meta": {
                    "mode": "deep",
                    "actual_start": batch_plan["actual_start"],
                    "actual_end": batch_plan["actual_end"],
                    "selected_count": batch_plan["selected_count"],
                    "batch_count": len(batches),
                },
                "ledgers": ledgers,
            }
        else:
            digest = build_page_window_digest(pages_input, int(start_page), int(end_page))
            if not digest["digest_text"]:
                st.warning("No readable text found in that page range. Check the page numbers or document text extraction.")
                return

            with st.spinner(
                f"Connecting themes across pages {digest['actual_start']}–{digest['actual_end']}..."
            ):
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
                    mode_label="Fast Overview",
                )
                st.session_state[state_key] = {
                    "markdown": formatted_md,
                    "meta": {
                        "mode": "fast",
                        "actual_start": digest["actual_start"],
                        "actual_end": digest["actual_end"],
                        "selected_count": digest["selected_count"],
                        "sampled_count": digest["sampled_count"],
                    },
                    "ledgers": [],
                }

        record_study_note(
            source="Page Range Synthesizer",
            title=f"{doc_title} (Pages {int(start_page)}–{int(end_page)})",
            explanation=st.session_state[state_key]["markdown"],
            command_notes="Connected multi-page puzzle pieces into a unified mental model and industry guide.",
        )
        st.toast("Saved multi-page puzzle synthesis to your session cheat-sheet!")

    saved = st.session_state.get(state_key)
    if saved and isinstance(saved, dict):
        meta = saved.get("meta", {})
        if meta.get("mode") == "deep":
            st.caption(
                f"Analyzed **all {meta.get('selected_count')} pages** "
                f"(pages **{meta.get('actual_start')}–{meta.get('actual_end')}**) across "
                f"**{meta.get('batch_count')} sequential batches**."
            )
        elif meta:
            st.caption(
                f"Sampled **{meta.get('sampled_count')} excerpts** across "
                f"**{meta.get('selected_count')} pages** "
                f"(pages **{meta.get('actual_start')}–{meta.get('actual_end')}**)."
            )

        st.markdown(saved.get("markdown", ""))

        ledgers = saved.get("ledgers") or []
        if ledgers:
            with st.expander("🔍 Inspect Extracted Puzzle Pieces per 20-Page Block", expanded=False):
                for item in ledgers:
                    st.markdown(f"**{item['span']}**")
                    st.markdown(item["ledger"])
                    st.markdown("---")
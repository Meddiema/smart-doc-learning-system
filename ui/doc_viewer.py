import os
import json
import streamlit as st
from streamlit_session_browser_storage import SessionStorage
from core.pdf_processor import save_uploaded_pdf, list_saved_pdfs, extract_pdf_pages, UPLOAD_DIR
from core.ai_client import AIClient

EXPLAINER_SYSTEM_PROMPT = """
You are an expert software engineering tutor. When given a highlighted snippet from a technical manual or code doc, explain it clearly using this exact structure:
1. **Plain English Summary** — What it means simply.
2. **How It Works** — Step-by-step breakdown.
3. **Where & When to Use It** — Practical real-world use cases.
4. **Simple Code Example** — Clean, runnable example demonstrating the concept.
5. **Common Pitfalls** — Mistakes beginners make here.
"""

DRAFT_KEY = "doc_viewer_temp_draft"


@st.cache_data(show_spinner=False)
def _cached_extract_pages(pdf_path: str, file_mtime: float):
    """Cache parsed PDF pages in RAM so page flips and reruns are instant."""
    return extract_pdf_pages(pdf_path)


def _restore_browser_draft(session_storage: SessionStorage):
    """Restore temporary highlight & explanation into session_state after a reconnect."""
    if st.session_state.get("_doc_draft_restored"):
        return

    raw_draft = session_storage.getItem(DRAFT_KEY)
    if raw_draft:
        try:
            draft = json.loads(raw_draft) if isinstance(raw_draft, str) else raw_draft
            if isinstance(draft, dict):
                st.session_state.setdefault("doc_selected_pdf", draft.get("selected_pdf", ""))
                st.session_state.setdefault("doc_page_num", int(draft.get("page_num", 1)))
                st.session_state.setdefault("doc_highlight_input", draft.get("highlighted_text", ""))
                st.session_state.setdefault("doc_followup_input", draft.get("follow_up", ""))
                if draft.get("explanation"):
                    st.session_state.setdefault("last_explanation", draft["explanation"])
                st.session_state["_doc_draft_restored"] = True
        except Exception:
            pass


def _save_browser_draft(
    session_storage: SessionStorage,
    selected_pdf: str,
    page_num: int,
    highlighted_text: str,
    follow_up: str,
    explanation: str,
):
    """Store active reading state in browser tab memory (auto-clears when tab closes)."""
    payload = {
        "selected_pdf": selected_pdf,
        "page_num": page_num,
        "highlighted_text": highlighted_text,
        "follow_up": follow_up,
        "explanation": explanation,
    }
    session_storage.setItem(DRAFT_KEY, json.dumps(payload))


@st.fragment
def _render_reader_and_explainer(saved_pdfs: list[str], session_storage: SessionStorage):
    default_pdf = st.session_state.get("doc_selected_pdf", "")
    default_index = saved_pdfs.index(default_pdf) if default_pdf in saved_pdfs else 0

    selected_pdf = st.selectbox(
        "Select a document from your library:",
        saved_pdfs,
        index=default_index,
        key="doc_selected_pdf",
    )
    pdf_path = os.path.join(UPLOAD_DIR, selected_pdf)
    file_mtime = os.path.getmtime(pdf_path) if os.path.exists(pdf_path) else 0.0

    pages = _cached_extract_pages(pdf_path, file_mtime)
    total_pages = max(1, len(pages))

    saved_page = int(st.session_state.get("doc_page_num", 1))
    safe_page = min(max(1, saved_page), total_pages)

    col_reader, col_explainer = st.columns([1.1, 1])

    with col_reader:
        st.subheader("📄 Page Reader")
        page_num = st.number_input(
            "Page Number",
            min_value=1,
            max_value=total_pages,
            value=safe_page,
            step=1,
            key="doc_page_num",
        )
        st.caption(f"Showing page {page_num} of {total_pages}")
        current_text = pages[page_num - 1]["text"] if pages else ""
        st.text_area(
            "Extracted Page Text (Copy any section to explain):",
            value=current_text,
            height=420,
        )

    with col_explainer:
        header_col, clear_col = st.columns([3, 1])
        with header_col:
            st.subheader("💡 Highlight Explainer")
        with clear_col:
            if st.button("🧹 Clear", help="Clear temporary highlight and explanation", use_container_width=True):
                for k in ("doc_highlight_input", "doc_followup_input", "last_explanation", "_doc_draft_restored"):
                    st.session_state.pop(k, None)
                session_storage.deleteItem(DRAFT_KEY)
                st.rerun(scope="fragment")

        highlighted_text = st.text_area(
            "Paste the specific paragraph, syntax, or concept you want simplified:",
            height=150,
            placeholder="Paste text from the page reader on the left...",
            key="doc_highlight_input",
        )
        follow_up = st.text_input(
            "Optional specific question:",
            placeholder="e.g., How does this connect to Flask routes?",
            key="doc_followup_input",
        )

        if st.button("✨ Explain Highlighted Concept", type="primary", use_container_width=True):
            if not highlighted_text.strip():
                st.warning("Paste a snippet first so the AI knows what to explain.")
            else:
                with st.spinner("Breaking down concept..."):
                    ai = AIClient()
                    prompt = f"Document: {selected_pdf} (Page {page_num})\n\nHighlighted Snippet:\n{highlighted_text}"
                    if follow_up.strip():
                        prompt += f"\n\nSpecific Question: {follow_up}"
                    explanation = ai.ask(prompt, system_instruction=EXPLAINER_SYSTEM_PROMPT)
                    st.session_state["last_explanation"] = explanation
                    _save_browser_draft(
                        session_storage=session_storage,
                        selected_pdf=selected_pdf,
                        page_num=page_num,
                        highlighted_text=highlighted_text,
                        follow_up=follow_up,
                        explanation=explanation,
                    )

        if "last_explanation" in st.session_state:
            st.markdown("---")
            st.markdown(st.session_state["last_explanation"])


def render_doc_viewer():
    st.header("📖 Document Library & Highlight Explainer")

    session_storage = SessionStorage()
    _restore_browser_draft(session_storage)

    # Upload section
    uploaded_file = st.file_uploader("Upload a PDF manual or documentation", type=["pdf"])
    if uploaded_file is not None:
        saved_path = save_uploaded_pdf(uploaded_file)
        st.success(f"Saved **{os.path.basename(saved_path)}** to your library!")

    saved_pdfs = list_saved_pdfs()
    if not saved_pdfs:
        st.info("Upload your first PDF above to start reading and highlighting concepts.")
        return

    _render_reader_and_explainer(saved_pdfs, session_storage)
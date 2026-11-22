import os
import re
import json
import streamlit as st
from streamlit_session_browser_storage import SessionStorage
from core.pdf_processor import save_uploaded_pdf, list_saved_pdfs, extract_pdf_pages, UPLOAD_DIR
from core.ai_client import AIClient

TRANSLATOR_SYSTEM_PROMPT = """
You are an expert software engineering and cybersecurity tutor.
When given a highlighted snippet from a technical manual, networking guide, or code doc, translate it into THREE formats and return ONLY strictly valid JSON (no markdown fences outside the JSON, no extra commentary):

{
  "explanation": "Structured markdown explanation covering: 1. Plain English Summary, 2. How It Works, 3. Where & When to Use It, 4. Common Pitfalls.",
  "code_lang": "python",
  "code": "Clean, runnable, well-commented code demonstrating the concept (use the most relevant language such as python, csharp, php, sql, or javascript).",
  "command": "Practical terminal/CLI commands (Linux bash, Windows CMD/PowerShell, Nmap, netstat, curl, git, or CVE lookup) that apply this concept in practice. Always use safe non-destructive targets like 192.168.1.1 or localhost.",
  "command_notes": "Brief bullet points explaining what each flag/argument in the command does."
}
"""

DRAFT_KEY = "doc_viewer_temp_draft"


@st.cache_data(show_spinner=False)
def _cached_extract_pages(pdf_path: str, file_mtime: float):
    """Cache parsed PDF pages in RAM so page flips and reruns are instant."""
    return extract_pdf_pages(pdf_path)


def _parse_ai_bundle(raw_response: str) -> dict:
    """Safely extract JSON fields from the AI response with graceful fallback."""
    cleaned = raw_response.strip()
    # Strip optional ```json ... ``` wrapper if the model includes one
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and any(k in data for k in ("explanation", "code", "command")):
            return {
                "explanation": data.get("explanation", "No explanation generated."),
                "code_lang": data.get("code_lang", "python") or "python",
                "code": data.get("code", "# No code snippet applicable for this concept."),
                "command": data.get("command", "# No terminal command applicable for this concept."),
                "command_notes": data.get("command_notes", ""),
            }
    except Exception:
        pass

    # Fallback if rate-limit notice or plain markdown was returned
    return {
        "explanation": raw_response,
        "code_lang": "python",
        "code": "# Switch to Explain view or re-run when rate limit clears.",
        "command": "# Switch to Explain view or re-run when rate limit clears.",
        "command_notes": "",
    }


def _restore_browser_draft(session_storage: SessionStorage):
    """Restore temporary highlight, toggle state, and AI outputs after a reconnect."""
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
                st.session_state.setdefault("doc_view_mode", draft.get("view_mode", "🔤 Explain"))
                if draft.get("ai_bundle"):
                    st.session_state.setdefault("last_ai_bundle", draft["ai_bundle"])
                st.session_state["_doc_draft_restored"] = True
        except Exception:
            pass


def _save_browser_draft(
    session_storage: SessionStorage,
    selected_pdf: str,
    page_num: int,
    highlighted_text: str,
    follow_up: str,
    view_mode: str,
    ai_bundle: dict,
):
    """Store active reading state in browser tab memory (auto-clears when tab closes)."""
    payload = {
        "selected_pdf": selected_pdf,
        "page_num": page_num,
        "highlighted_text": highlighted_text,
        "follow_up": follow_up,
        "view_mode": view_mode,
        "ai_bundle": ai_bundle,
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
            "Extracted Page Text (Copy any section to translate or explain):",
            value=current_text,
            height=440,
        )

    with col_explainer:
        header_col, clear_col = st.columns([3, 1])
        with header_col:
            st.subheader("💡 Highlight → Code / Command")
        with clear_col:
            if st.button("🧹 Clear", help="Clear temporary highlight and output", use_container_width=True):
                for k in (
                    "doc_highlight_input",
                    "doc_followup_input",
                    "last_ai_bundle",
                    "doc_view_mode",
                    "_doc_draft_restored",
                ):
                    st.session_state.pop(k, None)
                session_storage.deleteItem(DRAFT_KEY)
                st.rerun(scope="fragment")

        highlighted_text = st.text_area(
            "Paste plain-English concept, networking step, or syntax:",
            height=140,
            placeholder="Paste text from the page reader on the left...",
            key="doc_highlight_input",
        )
        follow_up = st.text_input(
            "Optional specific question or target language:",
            placeholder="e.g., Show this in Python sockets or Nmap CLI",
            key="doc_followup_input",
        )

        if st.button("✨ Translate & Explain Concept", type="primary", use_container_width=True):
            if not highlighted_text.strip():
                st.warning("Paste a snippet first so the AI knows what to translate.")
            else:
                with st.spinner("Generating Explanation, Code & Command..."):
                    ai = AIClient()
                    prompt = f"Document: {selected_pdf} (Page {page_num})\n\nHighlighted Snippet:\n{highlighted_text}"
                    if follow_up.strip():
                        prompt += f"\n\nSpecific Question / Preference: {follow_up}"

                    raw_response = ai.ask(prompt, system_instruction=TRANSLATOR_SYSTEM_PROMPT)
                    bundle = _parse_ai_bundle(raw_response)
                    st.session_state["last_ai_bundle"] = bundle

                    active_mode = st.session_state.get("doc_view_mode", "🔤 Explain")
                    _save_browser_draft(
                        session_storage=session_storage,
                        selected_pdf=selected_pdf,
                        page_num=page_num,
                        highlighted_text=highlighted_text,
                        follow_up=follow_up,
                        view_mode=active_mode,
                        ai_bundle=bundle,
                    )

        if "last_ai_bundle" in st.session_state:
            bundle = st.session_state["last_ai_bundle"]
            st.markdown("---")

            view_mode = st.radio(
                "Switch Output View (instant — no extra AI call):",
                ["🔤 Explain", "💻 Show Code", "⌨️ Show Command"],
                horizontal=True,
                key="doc_view_mode",
            )

            if view_mode == "🔤 Explain":
                st.markdown(bundle.get("explanation", ""))
            elif view_mode == "💻 Show Code":
                st.code(
                    bundle.get("code", ""),
                    language=bundle.get("code_lang", "python"),
                )
            elif view_mode == "⌨️ Show Command":
                st.code(bundle.get("command", ""), language="bash")
                if bundle.get("command_notes"):
                    st.markdown("**Command Breakdown:**")
                    st.markdown(bundle["command_notes"])


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
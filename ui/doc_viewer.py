import os
import re
import json
import streamlit as st
from streamlit_session_browser_storage import SessionStorage
from core.pdf_processor import (
    save_uploaded_pdf,
    list_saved_pdfs,
    get_pdf_pages,
    delete_saved_pdf,
    get_pdf_retention_info,
    renew_saved_pdf,
    UPLOAD_DIR,
)
from core.ai_client import AIClient
from core.cheat_sheet_exporter import record_study_note, render_cheat_sheet_download
from database.error_bank_db import add_error

try:
    from ui.range_synthesis_panel import render_range_synthesis_panel
except Exception:
    render_range_synthesis_panel = None

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

QUIZ_SYSTEM_PROMPT = """
You are an expert computer science and cybersecurity examiner.
Generate 4 active-recall questions from the provided study material (mix conceptual multiple-choice and practical CLI/code fill-in-the-blank questions).
Return ONLY strictly valid JSON (no markdown fences outside the JSON, no extra commentary):

{
  "questions": [
    {
      "id": "q1",
      "type": "mcq",
      "question": "Clear technical question testing deep understanding?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Option B",
      "explanation": "Concise explanation of why Option B is correct and why the others fail."
    },
    {
      "id": "q2",
      "type": "cli",
      "question": "Complete the command to show only open ports on 192.168.1.1: nmap _____ 192.168.1.1",
      "options": ["--open", "-sU", "-sn", "--closed"],
      "answer": "--open",
      "explanation": "The --open flag instructs Nmap to display only open (or possibly open) ports."
    }
  ]
}
"""

DRAFT_KEY = "doc_viewer_temp_draft"


@st.cache_data(ttl=300, show_spinner=False)
def _cached_get_pdf_pages(filename: str, disk_mtime: float, has_turso_marker: bool):
    """Cache parsed PDF pages in RAM so page flips and reruns are instant."""
    return get_pdf_pages(filename)


def _search_pdf_pages(pages: list[dict], query: str) -> list[dict]:
    """Scan already-cached PDF pages in Python (zero API cost) and return matching page hits."""
    clean_query = (query or "").strip()
    if len(clean_query) < 2:
        return []

    pattern = re.compile(re.escape(clean_query), re.IGNORECASE)
    matches = []
    for idx, page in enumerate(pages, start=1):
        text = page.get("text", "")
        found = list(pattern.finditer(text))
        if found:
            first_start = found[0].start()
            snippet_start = max(0, first_start - 45)
            snippet_end = min(len(text), first_start + len(clean_query) + 75)
            snippet = re.sub(r"\s+", " ", text[snippet_start:snippet_end]).strip()
            if snippet_start > 0:
                snippet = f"...{snippet}"
            if snippet_end < len(text):
                snippet = f"{snippet}..."
            matches.append({
                "page_num": page.get("page_num", idx),
                "count": len(found),
                "snippet": snippet,
            })
    return matches


def _strip_json_fences(raw_response: str) -> str:
    cleaned = raw_response.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    return re.sub(r"\s*```$", "", cleaned)


def _parse_ai_bundle(raw_response: str) -> dict:
    """Safely extract JSON fields from the AI response with graceful fallback."""
    cleaned = _strip_json_fences(raw_response)
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

    return {
        "explanation": raw_response,
        "code_lang": "python",
        "code": "# Switch to Explain view or re-run when rate limit clears.",
        "command": "# Switch to Explain view or re-run when rate limit clears.",
        "command_notes": "",
    }


def _parse_quiz_bundle(raw_response: str) -> tuple[list[dict], str]:
    """Parse generated quiz questions or return an error/rate-limit message."""
    cleaned = _strip_json_fences(raw_response)
    try:
        data = json.loads(cleaned)
        questions = data.get("questions", []) if isinstance(data, dict) else []
        valid_questions = [
            q for q in questions
            if isinstance(q, dict) and q.get("question") and q.get("options") and q.get("answer")
        ]
        if valid_questions:
            return valid_questions, ""
    except Exception:
        pass
    return [], raw_response


def _log_missed_question_to_error_bank(
    source_doc: str,
    page_num: int,
    question_obj: dict,
    user_answer: str,
):
    """Save a missed active-recall quiz question into error_bank (auto-expires after 15 days)."""
    category = "CLI / Security" if question_obj.get("type") == "cli" else "Concept Recall"
    error_title = f"[{source_doc} p.{page_num}] {question_obj['question'][:90]}"
    broken_code = f"Question:\n{question_obj['question']}\n\nSelected Answer:\n{user_answer}"
    error_message = f"Incorrect Quiz Answer: chose '{user_answer}' instead of '{question_obj['answer']}'"
    ai_diagnosis = question_obj.get("explanation", "Review this concept in your study manual.")
    fixed_code = question_obj["answer"]

    try:
        add_error(
            language=category,
            error_title=error_title,
            broken_code=broken_code,
            error_message=error_message,
            ai_diagnosis=ai_diagnosis,
            fixed_code=fixed_code,
        )
    except Exception as exc:
        st.toast(f"Could not save missed question to Error Bank: {exc}")


def _restore_browser_draft(session_storage: SessionStorage):
    """Restore temporary highlight, toggle state, quiz, and AI outputs after a reconnect."""
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
                if draft.get("quiz_questions"):
                    st.session_state.setdefault("active_page_quiz", draft["quiz_questions"])
                if draft.get("study_session_notes"):
                    st.session_state.setdefault("study_session_notes", draft["study_session_notes"])
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
    ai_bundle: dict | None,
    quiz_questions: list[dict] | None = None,
):
    """Store active reading, quiz, and cheat-sheet state in browser tab memory."""
    payload = {
        "selected_pdf": selected_pdf,
        "page_num": page_num,
        "highlighted_text": highlighted_text,
        "follow_up": follow_up,
        "view_mode": view_mode,
        "ai_bundle": ai_bundle,
        "quiz_questions": quiz_questions or [],
        "study_session_notes": st.session_state.get("study_session_notes", []),
    }
    session_storage.setItem(DRAFT_KEY, json.dumps(payload))


def _clear_doc_viewer_state(session_storage: SessionStorage):
    for k in list(st.session_state.keys()):
        if k in (
            "doc_highlight_input",
            "doc_followup_input",
            "doc_search_query",
            "last_ai_bundle",
            "doc_view_mode",
            "active_page_quiz",
            "quiz_graded_results",
            "_doc_draft_restored",
        ) or "_result_" in k:
            st.session_state.pop(k, None)
    try:
        session_storage.deleteItem(DRAFT_KEY)
    except Exception:
        pass


@st.fragment
def _render_reader_and_explainer(saved_pdfs: list[str], session_storage: SessionStorage):
    default_pdf = st.session_state.get("doc_selected_pdf", "")
    default_index = saved_pdfs.index(default_pdf) if default_pdf in saved_pdfs else 0

    col_select, col_renew, col_delete = st.columns([3.4, 1.1, 1.1])
    with col_select:
        selected_pdf = st.selectbox(
            "Select a document from your library:",
            saved_pdfs,
            index=default_index,
            key="doc_selected_pdf",
        )

    retention = get_pdf_retention_info(selected_pdf)

    with col_renew:
        st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button(
            "🔄 Renew 7d",
            use_container_width=True,
            help=f"Extend retention by 7 days (currently expires {retention['expires_label']})",
        ):
            renew_saved_pdf(selected_pdf)
            st.toast(f"Extended {selected_pdf} by 7 days!")
            st.rerun(scope="fragment")

    with col_delete:
        st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🗑️ Delete PDF", use_container_width=True, help="Remove this PDF from Turso and local storage"):
            delete_saved_pdf(selected_pdf)
            _cached_get_pdf_pages.clear()
            st.session_state.pop("doc_selected_pdf", None)
            st.session_state.pop("doc_page_num", None)
            _clear_doc_viewer_state(session_storage)
            st.toast(f"Deleted {selected_pdf}")
            st.rerun()

    pdf_path = os.path.join(UPLOAD_DIR, os.path.basename(selected_pdf))
    file_mtime = os.path.getmtime(pdf_path) if os.path.exists(pdf_path) else 0.0

    pages = _cached_get_pdf_pages(selected_pdf, file_mtime, True)
    total_pages = max(1, len(pages))

    saved_page = int(st.session_state.get("doc_page_num", 1))
    safe_page = min(max(1, saved_page), total_pages)

    col_reader, col_explainer = st.columns([1.1, 1])

    with col_reader:
        st.subheader("📄 Page Reader")

        # --- Zero-API-Cost Keyword Search & Jump-to-Page ---
        search_col, clear_search_col = st.columns([4, 1])
        with search_col:
            search_query = st.text_input(
                "Search inside PDF:",
                placeholder="🔍 Jump to keyword (e.g., subnet, OAuth, Nmap, SQL)...",
                key="doc_search_query",
                label_visibility="collapsed",
            )
        with clear_search_col:
            if search_query and st.button("✖", key="btn_clear_pdf_search", help="Clear search", use_container_width=True):
                st.session_state["doc_search_query"] = ""
                st.rerun(scope="fragment")

        if search_query.strip():
            hits = _search_pdf_pages(pages, search_query)
            if not hits:
                st.caption(f"No matches found for **{search_query.strip()}**.")
            else:
                total_occurrences = sum(h["count"] for h in hits)
                st.caption(
                    f"Found **{total_occurrences}** match(es) across **{len(hits)}** page(s) — click a page to jump:"
                )
                visible_hits = hits[:12]
                cols_per_row = 6
                for row_start in range(0, len(visible_hits), cols_per_row):
                    row_hits = visible_hits[row_start : row_start + cols_per_row]
                    btn_cols = st.columns(cols_per_row)
                    for col_idx, hit in enumerate(row_hits):
                        target_pg = hit["page_num"]
                        is_current = target_pg == safe_page
                        badge_label = f"p.{target_pg} ({hit['count']})"
                        with btn_cols[col_idx]:
                            if st.button(
                                badge_label,
                                key=f"jump_pg_{selected_pdf}_{target_pg}",
                                type="primary" if is_current else "secondary",
                                help=hit["snippet"],
                                use_container_width=True,
                            ):
                                st.session_state["doc_page_num"] = target_pg
                                st.rerun(scope="fragment")

                if len(hits) > 12:
                    remaining = ", ".join(f"p.{h['page_num']}" for h in hits[12:25])
                    st.caption(f"More matches on: {remaining}{'...' if len(hits) > 25 else ''}")

                active_hit = next((h for h in hits if h["page_num"] == safe_page), None)
                if active_hit:
                    st.info(f"**Page {safe_page} match preview:** {active_hit['snippet']}")

        page_num = st.number_input(
            "Page Number",
            min_value=1,
            max_value=total_pages,
            value=safe_page,
            step=1,
            key="doc_page_num",
        )
        st.caption(
            f"Showing page {page_num} of {total_pages} • {retention['badge']} (expires {retention['expires_label']})"
        )
        current_text = pages[page_num - 1]["text"] if pages else ""
        st.text_area(
            "Extracted Page Text (Copy any section to translate, explain, or quiz):",
            value=current_text,
            height=440,
        )

    with col_explainer:
        header_col, clear_col = st.columns([3, 1])
        with header_col:
            st.subheader("💡 Highlight → Code / Command")
        with clear_col:
            if st.button("🧹 Clear", help="Clear temporary highlight, quiz, and output", use_container_width=True):
                _clear_doc_viewer_state(session_storage)
                st.rerun(scope="fragment")

        highlighted_text = st.text_area(
            "Paste plain-English concept, networking step, or syntax:",
            height=130,
            placeholder="Paste text from the page reader on the left (or leave empty to quiz the whole page)...",
            key="doc_highlight_input",
        )
        follow_up = st.text_input(
            "Optional specific question or target language:",
            placeholder="e.g., Show this in Python sockets or Nmap CLI",
            key="doc_followup_input",
        )

        btn_translate, btn_quiz = st.columns(2)

        with btn_translate:
            if st.button("✨ Translate & Explain", type="primary", use_container_width=True):
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

                        # Record into session cheat-sheet automatically
                        snippet_preview = highlighted_text.strip().splitlines()[0][:65]
                        record_study_note(
                            source=f"{selected_pdf} (Page {page_num})",
                            title=snippet_preview,
                            explanation=bundle.get("explanation", ""),
                            code=bundle.get("code", ""),
                            code_lang=bundle.get("code_lang", "python"),
                            command=bundle.get("command", ""),
                            command_notes=bundle.get("command_notes", ""),
                        )

                        _save_browser_draft(
                            session_storage=session_storage,
                            selected_pdf=selected_pdf,
                            page_num=page_num,
                            highlighted_text=highlighted_text,
                            follow_up=follow_up,
                            view_mode=st.session_state.get("doc_view_mode", "🔤 Explain"),
                            ai_bundle=bundle,
                            quiz_questions=st.session_state.get("active_page_quiz", []),
                        )

        with btn_quiz:
            if st.button("📝 Quiz Me on This Page", use_container_width=True):
                source_material = highlighted_text.strip() or current_text.strip()
                if not source_material:
                    st.warning("This page has no readable text to generate a quiz from.")
                else:
                    with st.spinner("Generating 4 active-recall questions..."):
                        ai = AIClient()
                        quiz_prompt = (
                            f"Document: {selected_pdf} (Page {page_num})\n\n"
                            f"Study Material:\n{source_material[:3500]}"
                        )
                        raw_quiz = ai.ask(quiz_prompt, system_instruction=QUIZ_SYSTEM_PROMPT)
                        questions, err_msg = _parse_quiz_bundle(raw_quiz)

                        if err_msg:
                            st.warning(err_msg)
                        else:
                            st.session_state["active_page_quiz"] = questions
                            st.session_state.pop("quiz_graded_results", None)
                            _save_browser_draft(
                                session_storage=session_storage,
                                selected_pdf=selected_pdf,
                                page_num=page_num,
                                highlighted_text=highlighted_text,
                                follow_up=follow_up,
                                view_mode=st.session_state.get("doc_view_mode", "🔤 Explain"),
                                ai_bundle=st.session_state.get("last_ai_bundle"),
                                quiz_questions=questions,
                            )

        # --- Section A: Active Recall Quiz (Local Grading + Auto Error Bank Logging) ---
        if st.session_state.get("active_page_quiz"):
            st.markdown("---")
            st.markdown("### 🧠 Active Recall Quiz")
            st.caption("Missed questions auto-log to your **Personal Error Bank** (auto-deleted after 15 days).")

            questions = st.session_state["active_page_quiz"]
            with st.form(key=f"quiz_form_{selected_pdf}_{page_num}"):
                user_choices = {}
                for idx, q in enumerate(questions, start=1):
                    badge = "⌨️ CLI / Code" if q.get("type") == "cli" else "📘 Concept"
                    st.markdown(f"**Q{idx} ({badge}):** {q['question']}")
                    user_choices[q["id"]] = st.radio(
                        f"Select answer for Q{idx}:",
                        q["options"],
                        index=None,
                        key=f"quiz_ans_{selected_pdf}_{page_num}_{q['id']}",
                        label_visibility="collapsed",
                    )

                submitted = st.form_submit_button("✅ Grade Quiz (Instant)", type="primary", use_container_width=True)

            if submitted:
                if any(ans is None for ans in user_choices.values()):
                    st.warning("Please answer all questions before grading.")
                else:
                    score = 0
                    results = []
                    for q in questions:
                        chosen = user_choices[q["id"]]
                        correct = q["answer"]
                        is_right = chosen.strip() == correct.strip()
                        if is_right:
                            score += 1
                        else:
                            _log_missed_question_to_error_bank(
                                source_doc=selected_pdf,
                                page_num=page_num,
                                question_obj=q,
                                user_answer=chosen,
                            )
                        results.append({
                            "question": q["question"],
                            "chosen": chosen,
                            "correct": correct,
                            "is_right": is_right,
                            "explanation": q.get("explanation", ""),
                        })
                    st.session_state["quiz_graded_results"] = {
                        "score": score,
                        "total": len(questions),
                        "details": results,
                    }

                    quiz_summary_lines = [
                        f"- **{'✅' if r['is_right'] else '❌'} {r['question']}** → Answer: `{r['correct']}` ({r['explanation']})"
                        for r in results
                    ]
                    record_study_note(
                        source=f"Active Recall Quiz • {selected_pdf} (Page {page_num})",
                        title=f"Quiz Review ({score}/{len(questions)} Score)",
                        explanation="\n".join(quiz_summary_lines),
                    )
                    _save_browser_draft(
                        session_storage=session_storage,
                        selected_pdf=selected_pdf,
                        page_num=page_num,
                        highlighted_text=highlighted_text,
                        follow_up=follow_up,
                        view_mode=st.session_state.get("doc_view_mode", "🔤 Explain"),
                        ai_bundle=st.session_state.get("last_ai_bundle"),
                        quiz_questions=questions,
                    )

            if "quiz_graded_results" in st.session_state:
                graded = st.session_state["quiz_graded_results"]
                score, total = graded["score"], graded["total"]
                if score == total:
                    st.success(f"🎉 Perfect Score: **{score}/{total}**! Zero errors logged.")
                else:
                    missed_count = total - score
                    st.warning(
                        f"Score: **{score}/{total}** — Logged **{missed_count}** missed concept(s) "
                        f"to your **Personal Error Bank** (kept for 15 days)."
                    )

                for idx, item in enumerate(graded["details"], start=1):
                    if item["is_right"]:
                        st.markdown(f"✅ **Q{idx}:** Correct (`{item['correct']}`) — {item['explanation']}")
                    else:
                        st.markdown(
                            f"❌ **Q{idx}:** You chose `{item['chosen']}` | Correct: **`{item['correct']}`**\n"
                            f"> 💡 {item['explanation']}"
                        )

        # --- Section B: Explain / Show Code / Show Command Output ---
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
                code_snippet = bundle.get("code", "")
                code_lang = bundle.get("code_lang", "python")
                st.code(code_snippet, language=code_lang)

                if st.button("⚡ Load into Try-It Sandbox", use_container_width=True, key="btn_send_doc_code_sandbox"):
                    st.session_state["last_highlighted_snippet"] = (
                        f"Language: {code_lang}\n"
                        f"Source: {selected_pdf} (Page {page_num})\n\n"
                        f"```{code_lang}\n{code_snippet}\n```"
                    )
                    st.session_state["sandbox_prefill_code"] = code_snippet
                    st.session_state["sandbox_prefill_lang"] = code_lang
                    st.info("Code loaded! Open **⚡ Interactive Try-It Sandbox** in the sidebar to run or modify it.")
            elif view_mode == "⌨️ Show Command":
                st.code(bundle.get("command", ""), language="bash")
                if bundle.get("command_notes"):
                    st.markdown("**Command Breakdown:**")
                    st.markdown(bundle["command_notes"])

        # --- Section C: Multi-Page Flow & Industry Synthesis (Pages 1..N) ---
        if render_range_synthesis_panel is not None:
            st.markdown("---")
            with st.expander("🧭 Multi-Page Flow & Industry Synthesis (Pages 1–100+)", expanded=False):
                safe_doc_key = re.sub(r"[^A-Za-z0-9_-]+", "_", selected_pdf)
                render_range_synthesis_panel(
                    pages_input=pages,
                    doc_title=selected_pdf,
                    total_pages=total_pages,
                    key_prefix=f"range_synth_{safe_doc_key}",
                )

        # --- Section D: 1-Click Offline Cheat-Sheet Export (Zero API Cost) ---
        st.markdown("---")
        render_cheat_sheet_download(location_key="doc_viewer")


def render_doc_viewer():
    st.header("📖 Document Library & Highlight Explainer")
    st.caption("Uploaded PDFs are persisted in Turso across reboots, auto-expire after **7 days**, or can be deleted anytime.")

    session_storage = SessionStorage()
    _restore_browser_draft(session_storage)

    # Upload section
    uploaded_file = st.file_uploader("Upload a PDF manual or documentation", type=["pdf"])
    if uploaded_file is not None:
        saved_path = save_uploaded_pdf(uploaded_file)
        _cached_get_pdf_pages.clear()
        st.success(f"Saved **{os.path.basename(saved_path)}** to your library (7-day retention)!")

    saved_pdfs = list_saved_pdfs()
    if not saved_pdfs:
        st.info("Upload your first PDF above to start reading and highlighting concepts.")
        return

    _render_reader_and_explainer(saved_pdfs, session_storage)
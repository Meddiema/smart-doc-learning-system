import os
import streamlit as st
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

def render_doc_viewer():
    st.header("📖 Document Library & Highlight Explainer")

    # Upload section
    uploaded_file = st.file_uploader("Upload a PDF manual or documentation", type=["pdf"])
    if uploaded_file is not None:
        saved_path = save_uploaded_pdf(uploaded_file)
        st.success(f"Saved **{os.path.basename(saved_path)}** to your library!")

    saved_pdfs = list_saved_pdfs()
    if not saved_pdfs:
        st.info("Upload your first PDF above to start reading and highlighting concepts.")
        return

    selected_pdf = st.selectbox("Select a document from your library:", saved_pdfs)
    pdf_path = os.path.join(UPLOAD_DIR, selected_pdf)

    pages = extract_pdf_pages(pdf_path)
    total_pages = len(pages)

    col_reader, col_explainer = st.columns([1.1, 1])

    with col_reader:
        st.subheader("📄 Page Reader")
        page_num = st.number_input("Page Number", min_value=1, max_value=total_pages, value=1, step=1)
        st.caption(f"Showing page {page_num} of {total_pages}")
        current_text = pages[page_num - 1]["text"]
        st.text_area("Extracted Page Text (Copy any section to explain):", value=current_text, height=420)

    with col_explainer:
        st.subheader("💡 Highlight Explainer")
        highlighted_text = st.text_area(
            "Paste the specific paragraph, syntax, or concept you want simplified:",
            height=150,
            placeholder="Paste text from the page reader on the left..."
        )
        follow_up = st.text_input(
            "Optional specific question:",
            placeholder="e.g., How does this connect to Flask routes?"
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

        if "last_explanation" in st.session_state:
            st.markdown("---")
            st.markdown(st.session_state["last_explanation"])
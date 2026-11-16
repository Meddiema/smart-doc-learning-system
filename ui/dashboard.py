import streamlit as st
from core.pdf_processor import list_saved_pdfs
from database.error_bank_db import get_error_stats, get_all_errors
from database.screenshots_db import get_all_screenshots

def render_dashboard():
    st.header("🏠 Smart Learning System — Command Center")
    st.write("Your unified **Read → Discuss → Try It Out → Master** engineering workspace.")

    pdfs = list_saved_pdfs()
    err_stats = get_error_stats()
    screenshots = get_all_screenshots()

    # Top KPI Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📖 PDFs in Library", len(pdfs))
    c2.metric("📉 Total Errors Logged", err_stats["total"])
    c3.metric("✅ Bugs Mastered", err_stats["mastered"])
    c4.metric("🖼️ Diagrams Analyzed", len(screenshots))

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📚 Recent Documents")
        if not pdfs:
            st.info("No PDFs uploaded yet. Head to **📖 Document Library** to add your first manual.")
        else:
            for pdf in pdfs[:5]:
                st.markdown(f"- 📄 `{pdf}`")

    with col_right:
        st.subheader("🟡 Active Bugs to Review")
        unmastered = get_all_errors(only_unmastered=True)
        if not unmastered:
            st.success("All logged bugs are mastered! Test new concepts in the **⚡ Interactive Try-It Sandbox**.")
        else:
            for err in unmastered[:5]:
                st.markdown(f"- **[{err['language']}]** {err['error_title']}")
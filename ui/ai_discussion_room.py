import streamlit as st
from core.discussion_engine import DiscussionEngine, PERSONAS

def render_ai_discussion_room():
    st.header("💬 Multi-AI Discussion Room")
    st.caption("Three specialized AI personas analyze your topic independently, debate gaps, and summarize key takeaways.")

    # Pre-fill context if the user came from the Document Viewer
    default_context = st.session_state.get("last_highlighted_snippet", "")

    topic = st.text_input(
        "What concept or question should the 3 AIs discuss?",
        placeholder="e.g., How does template inheritance work in Jinja2, and what happens if I forget super()?"
    )

    with st.expander("📎 Optional: Attach Document Context or Code Snippet", expanded=bool(default_context)):
        context = st.text_area(
            "Paste code or document text for the AIs to reference:",
            value=default_context,
            height=120
        )

    if st.button("🚀 Start 3-AI Roundtable", type="primary"):
        if not topic.strip():
            st.warning("Enter a topic or question first.")
            return

        with st.spinner("The 3 AIs are analyzing and debating your topic..."):
            engine = DiscussionEngine()
            st.session_state["discussion_result"] = engine.run_roundtable(topic, context)
            st.session_state["discussion_topic"] = topic

    if "discussion_result" in st.session_state:
        res = st.session_state["discussion_result"]
        st.markdown("---")
        st.subheader(f"Topic: {st.session_state.get('discussion_topic', '')}")

        # Step 1: Three Columns for Independent Views
        st.markdown("### 1️⃣ Independent Perspectives")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.info(f"**{PERSONAS['technical']['name']}**")
            st.markdown(res["technical"])

        with col2:
            st.success(f"**{PERSONAS['analogy']['name']}**")
            st.markdown(res["analogy"])

        with col3:
            st.warning(f"**{PERSONAS['big_picture']['name']}**")
            st.markdown(res["big_picture"])

        # Step 2: Roundtable Debate
        st.markdown("---")
        st.markdown("### 2️⃣ Live AI Roundtable Debate")
        st.markdown(res["debate"])

        # Step 3: Summary Panel
        st.markdown("---")
        st.markdown("### 3️⃣ Final Summary & Key Takeaways")
        st.markdown(res["summary"])
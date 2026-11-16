import os
import streamlit as st
from database.db_setup import init_db
from ui.auth_view import render_auth_view
from ui.dashboard import render_dashboard
from ui.doc_viewer import render_doc_viewer
from ui.ai_discussion_room import render_ai_discussion_room
from ui.try_it_sandbox import render_try_it_sandbox
from ui.error_bank_view import render_error_bank_view
from ui.screenshot_viewer import render_screenshot_viewer

st.set_page_config(
    page_title="Smart Document Learning System",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_css(file_path: str = os.path.join("assets", "styles.css")):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()
init_db()

# Initialize auth session state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Gatekeeper: Show Login screen if not authenticated
if not st.session_state["authenticated"]:
    render_auth_view()
    st.stop()

# Authenticated Sidebar Navigation
current_user = st.session_state.get("user", {}).get("username", "User")

with st.sidebar:
    st.title("📚 Smart Doc Learning")
    st.caption(f"👤 Signed in as **{current_user}**")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        [
            "🏠 Dashboard",
            "📖 Document Library",
            "💬 AI Discussion Room",
            "⚡ Interactive Try-It Sandbox",
            "📉 Personal Error Bank",
            "🖼️ Screenshot Analysis"
        ]
    )

    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state.pop("user", None)
        st.rerun()

# Page Routing
if page == "🏠 Dashboard":
    render_dashboard()
elif page == "📖 Document Library":
    render_doc_viewer()
elif page == "💬 AI Discussion Room":
    render_ai_discussion_room()
elif page == "⚡ Interactive Try-It Sandbox":
    render_try_it_sandbox()
elif page == "📉 Personal Error Bank":
    render_error_bank_view()
elif page == "🖼️ Screenshot Analysis":
    render_screenshot_viewer()
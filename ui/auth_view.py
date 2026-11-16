import streamlit as st
from database.auth_db import authenticate_user, register_user

def render_auth_view():
    """Render the login and registration screen."""
    _, center_col, _ = st.columns([1, 1.3, 1])

    with center_col:
        st.title("📚 Smart Document Learning")
        st.caption("Sign in to access your documents, AI discussion room, sandbox, and error bank.")
        st.markdown("---")

        tab_login, tab_register = st.tabs(["🔐 Login", "📝 Create Account"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

                if submitted:
                    user = authenticate_user(username, password)
                    if user:
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

        with tab_register:
            with st.form("register_form"):
                new_user = st.text_input("Choose a Username", placeholder="e.g., meddie")
                new_pass = st.text_input("Choose a Password", type="password", placeholder="Minimum 6 characters")
                confirm_pass = st.text_input("Confirm Password", type="password", placeholder="Re-enter password")
                reg_submitted = st.form_submit_button("Create Account", use_container_width=True)

                if reg_submitted:
                    if new_pass != confirm_pass:
                        st.error("Passwords do not match.")
                    else:
                        ok, msg = register_user(new_user, new_pass)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
import streamlit as st

def render_code_panel(
    code: str,
    language: str = "python",
    title: str = "Code Snippet",
    show_line_numbers: bool = True,
    allow_send_to_sandbox: bool = True,
    key_prefix: str = "code_card"
):
    """
    Renders a clean, syntax-highlighted code card with Streamlit's native
    copy-to-clipboard button and an optional 'Send to Sandbox' handoff.
    """
    if not code or not code.strip():
        return

    with st.container(border=True):
        header_col, btn_col = st.columns([3, 1])

        with header_col:
            st.markdown(f"**{title}** `{language.upper()}`")

        with btn_col:
            if allow_send_to_sandbox:
                if st.button("⚡ Test in Sandbox", key=f"{key_prefix}_send", use_container_width=True):
                    st.session_state["sandbox_code"] = code.strip()
                    st.session_state["sandbox_lang"] = language.capitalize()
                    st.toast("Code sent! Open ⚡ Interactive Try-It Sandbox to run it.")

        # st.code includes a built-in copy-to-clipboard icon in the top-right corner
        st.code(
            code.strip(),
            language=language.lower(),
            line_numbers=show_line_numbers
        )
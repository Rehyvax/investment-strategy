"""URL-token auth for the dashboard.

Retail-grade, NOT production banking-grade. Suitable for a 1-2 trusted
operator scenario (user + spouse / accountant). Tokens are configured
in `.streamlit/secrets.toml` under `[auth].valid_tokens`. Access is
granted when:

  https://<app>.streamlit.app/?token=<one of valid_tokens>

The app re-renders the login form for any other request. If no tokens
are configured (e.g. local dev without secrets.toml), the dashboard
runs in unauthenticated mode with a visible warning.
"""

from __future__ import annotations

import streamlit as st


def _valid_tokens() -> list[str]:
    try:
        return list(st.secrets.get("auth", {}).get("valid_tokens", []))
    except (FileNotFoundError, AttributeError):
        return []


def check_auth() -> bool:
    """Returns True when the request is authenticated (or dev-mode).
    Renders a login form otherwise."""
    valid = _valid_tokens()

    if not valid:
        st.warning(
            "Dev mode: no auth tokens configured. Copy "
            "`.streamlit/secrets.toml.template` to `.streamlit/secrets.toml` "
            "and set `[auth].valid_tokens` before deploying."
        )
        return True

    query_params = st.query_params
    token = query_params.get("token", "")
    if token and token in valid:
        return True

    st.title("Investment Dashboard")
    st.markdown("Acceso restringido. Introduce el token de acceso.")
    token_input = st.text_input(
        "Token", type="password", key="auth_token_input"
    )
    if st.button("Acceder", key="auth_login_btn"):
        if token_input in valid:
            st.query_params["token"] = token_input
            st.rerun()
        else:
            st.error("Token inválido.")
    return False

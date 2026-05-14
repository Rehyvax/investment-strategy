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

import os
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_env_once() -> None:
    """Populate `os.environ` from Streamlit secrets (Cloud) and `.env`
    (local) before any module reads `ANTHROPIC_API_KEY`.

    Idempotent: runs once at module import time. Streamlit re-uses the
    Python process across pages within a session, so this fires a
    single time per `streamlit run` lifecycle.

    Priority (highest first):
      1. Already-set `os.environ` value — never overridden.
      2. Streamlit Cloud `st.secrets`:
         - flat `ANTHROPIC_API_KEY = "..."`
         - nested `[anthropic] api_key = "..."`
      3. Local `.env` via python-dotenv (skipped if not installed)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return

    try:
        secrets = st.secrets
    except (FileNotFoundError, AttributeError):
        secrets = None

    if secrets is not None:
        candidate = ""
        try:
            candidate = str(secrets.get("ANTHROPIC_API_KEY", "") or "")
        except Exception:  # noqa: BLE001 — secrets may raise on bad TOML
            candidate = ""
        if not candidate:
            try:
                anthropic_block = secrets.get("anthropic", {})
                if isinstance(anthropic_block, dict):
                    candidate = str(anthropic_block.get("api_key", "") or "")
            except Exception:  # noqa: BLE001
                candidate = ""
        if candidate:
            os.environ["ANTHROPIC_API_KEY"] = candidate
            return

    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        pass


_bootstrap_env_once()


def _valid_tokens() -> list[str]:
    try:
        return list(st.secrets.get("auth", {}).get("valid_tokens", []))
    except (FileNotFoundError, AttributeError):
        return []


_SESSION_FLAG = "dashboard_auth_ok"


def check_auth() -> bool:
    """Returns True when the request is authenticated (or dev-mode).
    Renders a login form otherwise.

    Auth persistence model (in priority order):
      1. `st.session_state[_SESSION_FLAG]` — set once per browser tab.
         Survives page navigation in the Streamlit sidebar. Cleared
         when the user closes the tab.
      2. `?token=` query param — backwards compatible with old links.
         When valid, also sets the session flag so subsequent page
         changes don't re-prompt.
      3. Login form — falls back here on first hit without either."""
    valid = _valid_tokens()

    if not valid:
        st.warning(
            "Dev mode: no auth tokens configured. Copy "
            "`.streamlit/secrets.toml.template` to `.streamlit/secrets.toml` "
            "and set `[auth].valid_tokens` before deploying."
        )
        return True

    if st.session_state.get(_SESSION_FLAG):
        return True

    query_params = st.query_params
    token = query_params.get("token", "")
    if token and token in valid:
        st.session_state[_SESSION_FLAG] = True
        return True

    st.title("Investment Dashboard")
    st.markdown("Acceso restringido. Introduce el token de acceso.")
    token_input = st.text_input(
        "Token", type="password", key="auth_token_input"
    )
    if st.button("Acceder", key="auth_login_btn"):
        if token_input in valid:
            st.session_state[_SESSION_FLAG] = True
            st.query_params["token"] = token_input
            st.rerun()
        else:
            st.error("Token inválido.")
    return False

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


_BRIDGED_KEYS = (
    "ANTHROPIC_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_API_SECRET",
    "ALPACA_BASE_URL",
    "FINNHUB_API_KEY",
    "OPENBB_PAT",
    "FRED_API_KEY",
    "FMP_API_KEY",
)


def _walk_secrets_into_env(node: object, parent_key: str = "", depth: int = 0) -> None:
    """Recursively walk a Streamlit `Secrets` (or dict) tree and copy
    any leaf whose key matches a bridged env-var name into `os.environ`.

    Handles three real-world TOML layouts seen in Streamlit Cloud:
      (a) Top-level flat:        ANTHROPIC_API_KEY = "sk-ant-..."
      (b) Nested anthropic:      [anthropic] api_key = "sk-ant-..."
      (c) Accidentally nested:   `ANTHROPIC_API_KEY = "..."` placed
          AFTER a `[section]` header (a TOML pitfall) ends up as
          `section.ANTHROPIC_API_KEY` — we still find it.

    `os.environ.setdefault` is used so an already-set env var (local
    `.env`, OS env, container env) wins over secrets."""
    if depth > 4:
        return
    try:
        items = list(node.items())  # type: ignore[union-attr]
    except (AttributeError, TypeError):
        return

    for raw_key, value in items:
        key = str(raw_key)
        # Recurse into nested mappings (Streamlit nests as Secrets, not dict).
        if hasattr(value, "items") and not isinstance(value, (str, bytes)):
            _walk_secrets_into_env(value, parent_key=key, depth=depth + 1)
            continue
        # Leaf value — match against bridged keys.
        if not isinstance(value, (str, int, float, bool)):
            continue
        env_target: str | None = None
        upper = key.upper()
        if upper in _BRIDGED_KEYS:
            env_target = upper
        elif key.lower() == "api_key" and parent_key.lower() == "anthropic":
            env_target = "ANTHROPIC_API_KEY"
        if env_target and str(value).strip():
            os.environ.setdefault(env_target, str(value).strip())


def _bootstrap_env_once() -> None:
    """Populate `os.environ` from Streamlit secrets (Cloud) and `.env`
    (local) before any module reads `ANTHROPIC_API_KEY`.

    Idempotent: runs once at module import time. Streamlit re-uses the
    Python process across pages within a session, so this fires a
    single time per `streamlit run` lifecycle.

    Resolution order:
      1. Existing `os.environ` value — never overridden (handled by
         `_walk_secrets_into_env` via `setdefault`).
      2. Streamlit Cloud `st.secrets`, walked recursively so flat,
         nested, and accidentally-nested keys all bridge correctly.
      3. Local `.env` via python-dotenv (only if ANTHROPIC_API_KEY is
         still missing — local devs want .env to win over absent
         secrets, but Cloud values should win over absent .env)."""
    # Streamlit's secrets accessor raises StreamlitSecretNotFoundError
    # (inherits FileNotFoundError on recent versions, AttributeError on
    # older ones, or RuntimeError if the runtime context is missing).
    # Catch broadly so a misbehaving secrets layer never breaks auth.
    secrets = None
    try:
        secrets = st.secrets
    except Exception:  # noqa: BLE001 — defensive across Streamlit versions
        pass

    if secrets is not None:
        try:
            _walk_secrets_into_env(secrets)
        except Exception:  # noqa: BLE001 — defensive: never break the page
            pass
        # Fallback: materialize via `dict(secrets)` in case the live
        # Secrets object misbehaves on `.items()` (observed on some
        # streamlit-cloud snapshots). If `dict()` itself fails we are
        # already covered by the recursive walker above.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            try:
                _walk_secrets_into_env(dict(secrets))
            except Exception:  # noqa: BLE001
                pass

    if not os.environ.get("ANTHROPIC_API_KEY"):
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

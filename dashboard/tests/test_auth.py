"""Auth tests using streamlit.testing.v1.AppTest.

The auth module reads st.secrets which is empty in the test runner,
so the dev-mode path is exercised by default. The token-validation
path is tested by injecting secrets via the AppTest API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))


def test_no_secrets_dev_mode_allows_all():
    """Without configured tokens, check_auth() returns True and emits
    a dev-mode warning."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_dev_mode_runner)
    at.run()
    assert not at.exception
    # The warning is the dev-mode indicator; success message is the auth pass.
    warnings = [w.value for w in at.warning]
    assert any("Dev mode" in w for w in warnings)


def test_invalid_token_blocks_access():
    """With tokens configured and an invalid one in the URL, the login
    form is shown (check_auth returns False)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_token_runner)
    at.secrets["auth"] = {"valid_tokens": ["good-token"]}
    at.query_params["token"] = "wrong-token"
    at.run()
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Investment Dashboard" in t for t in titles)


def test_valid_token_passes():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_token_runner)
    at.secrets["auth"] = {"valid_tokens": ["good-token"]}
    at.query_params["token"] = "good-token"
    at.run()
    assert not at.exception
    successes = [s.value for s in at.success]
    assert any("authenticated" in s.lower() for s in successes)


# ----------------------------------------------------------------------
# Runner stubs — Streamlit AppTest needs callables.
# ----------------------------------------------------------------------
def _dev_mode_runner():
    import streamlit as st

    from auth import check_auth

    if check_auth():
        st.success("authenticated")


def _token_runner():
    import streamlit as st

    from auth import check_auth

    if check_auth():
        st.success("authenticated")

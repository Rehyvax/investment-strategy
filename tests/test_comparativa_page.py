"""Smoke tests for Pantalla 5 (Comparativa Portfolios)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = ROOT / "dashboard" / "pages" / "5_Comparativa.py"


def test_page_runs_without_exception():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGE_PATH))
    at.run(timeout=15)
    assert not at.exception, at.exception


def test_page_renders_ranking_section():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGE_PATH))
    at.run(timeout=15)
    text = "\n".join(m.value for m in at.markdown if m.value)
    assert "Ranking" in text
    assert "Comparativa de Portfolios" in text


def test_page_renders_attribution_placeholder():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGE_PATH))
    at.run(timeout=15)
    text = "\n".join(m.value for m in at.markdown if m.value)
    assert "Performance Attribution" in text
    assert "PENDIENTE" in text


def test_page_renders_per_portfolio_selectbox():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGE_PATH))
    at.run(timeout=15)
    selectbox_labels = [s.label for s in at.selectbox]
    assert any("cartera" in (lbl or "").lower() for lbl in selectbox_labels)

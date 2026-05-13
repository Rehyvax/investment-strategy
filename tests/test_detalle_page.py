"""Tests for Pantalla 3 — Detalle de Posición + supporting services
and the dynamic upcoming-events generator."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dashboard"))

PAGE_PATH = ROOT / "dashboard" / "pages" / "3_Detalle.py"


# ----------------------------------------------------------------------
# ThesisReader
# ----------------------------------------------------------------------
class TestThesisReader:
    def test_list_assets_non_empty(self):
        from services.thesis_reader import ThesisReader

        assets = ThesisReader().list_assets()
        # At least one of MELI / AXON / MSFT should be present.
        assert any(t in assets for t in ("MELI", "AXON", "MSFT"))

    def test_axon_authoritative_is_override(self):
        from services.thesis_reader import ThesisReader

        thesis = ThesisReader().get_authoritative_version("AXON")
        assert thesis is not None
        assert thesis.get("event_type") == "thesis_user_override_annotation"
        assert thesis.get("user_override_active") is True

    def test_meli_falsifier_includes_halfway(self):
        from services.thesis_reader import ThesisReader

        tr = ThesisReader()
        thesis = tr.get_latest_thesis_only("MELI")
        assert thesis is not None
        falsifiers = tr.get_falsifier_status(thesis)
        assert falsifiers, "MELI v3 should expose falsifiers"
        statuses = [f["status"] for f in falsifiers]
        assert any("halfway" in s for s in statuses)


# ----------------------------------------------------------------------
# PositionReader
# ----------------------------------------------------------------------
class TestPositionReader:
    def test_latest_snapshot_has_nav(self):
        from services.position_reader import PositionReader

        snap = PositionReader().get_latest_snapshot("real")
        assert snap is not None
        assert "nav_total_eur" in snap

    def test_list_assets_yields_held_tickers(self):
        from services.position_reader import PositionReader

        assets = PositionReader().list_assets("real")
        assert len(assets) >= 15

    def test_axon_position_has_weight_pct(self):
        from services.position_reader import PositionReader

        p = PositionReader().get_position("AXON", "real")
        assert p is not None
        # `weight_pct` is computed by the reader when the rebuilder
        # snapshot omits it.
        assert p["weight_pct"] > 0


# ----------------------------------------------------------------------
# Dynamic upcoming events — derived from yfinance + trades + theses,
# never hardcoded.
# ----------------------------------------------------------------------
class TestUpcomingEvents:
    def test_returns_list_for_any_ticker(self):
        from generate_cerebro_state import _get_upcoming_events_for_asset

        events = _get_upcoming_events_for_asset("MSFT", date(2026, 5, 14))
        assert isinstance(events, list)
        for evt in events:
            assert "date" in evt
            assert "event" in evt
            assert "source" in evt

    def test_meli_includes_tax_rule_window(self):
        """MELI sold at a loss 2026-05-12 → trades log should surface a
        `Fin 2-month rule` event with the matching window end."""
        from generate_cerebro_state import _get_upcoming_events_for_asset

        events = _get_upcoming_events_for_asset("MELI", date(2026, 5, 14))
        tax_rule = [e for e in events if e["source"] == "trades_log"]
        assert any(e["date"] == "2026-07-11" for e in tax_rule)


# ----------------------------------------------------------------------
# Page smoke test
# ----------------------------------------------------------------------
class TestDetallePage:
    def test_page_runs_without_exception(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(PAGE_PATH))
        at.query_params["asset"] = "AXON"
        at.run(timeout=20)
        assert not at.exception, at.exception

    def test_page_renders_for_meli(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(PAGE_PATH))
        at.query_params["asset"] = "MELI"
        at.run(timeout=20)
        text = "\n".join(m.value for m in at.markdown if m.value)
        assert "Tesis Vigente" in text
        assert "Eventos Próximos" in text
        assert "Opinión del Cerebro" in text

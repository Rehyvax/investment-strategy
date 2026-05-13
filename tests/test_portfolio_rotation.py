"""Regression tests for the 2026-05-14 portfolio rotation.

Covers:
  - AXON closed-position event correctly hides the thesis from
    `get_authoritative_version()` and registers in `get_closed_assets()`.
  - The new snapshot 2026-05-14 carries 19 positions and the user-reported
    NAV (€48,183.58 ± €5).
  - MELI's authoritative version is still the v3 thesis review event,
    not the size-change event appended afterwards.
  - The cerebro state generated for 2026-05-14 omits AXON from
    recommendations and from `upcoming_events_by_asset`.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dashboard"))

import generate_cerebro_state as gen  # noqa: E402
from services.thesis_reader import ThesisReader  # noqa: E402


SNAPSHOT_PATH = ROOT / "data" / "snapshots" / "real" / "2026-05-14.json"


class TestClosedPositions:
    def test_axon_marked_closed(self):
        tr = ThesisReader()
        closed = tr.get_closed_assets()
        assert "AXON" in closed, (
            "AXON should appear in get_closed_assets() after the "
            "thesis_closed_position event from 2026-05-14."
        )

    def test_axon_authoritative_returns_none(self):
        tr = ThesisReader()
        auth = tr.get_authoritative_version("AXON")
        assert auth is None, (
            "AXON authoritative version must be None — closed_position is "
            "terminal even when an active override exists upstream."
        )

    def test_is_closed_helper(self):
        tr = ThesisReader()
        assert tr.is_closed("AXON") is True
        # MELI is still held, just reduced — must not be flagged closed.
        assert tr.is_closed("MELI") is False
        # MSFT is still held, never had a closed event.
        assert tr.is_closed("MSFT") is False


class TestSnapshotRotation:
    def test_snapshot_file_exists(self):
        assert SNAPSHOT_PATH.exists(), (
            "Snapshot 2026-05-14 was not written by the rotation script."
        )

    def test_nav_within_tolerance(self):
        snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        nav = float(snap["nav_total_eur"])
        # Tolerance ±€5 — single-FX rounding drift is ~€1.20.
        assert 48178 < nav < 48189, f"NAV out of tolerance: {nav}"

    def test_position_count_19(self):
        snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert snap["positions_count"] == 19
        tickers = sorted(p["ticker"] for p in snap["positions"])
        # 4 NEW positions must be present.
        for t in ("VICR", "NVDA", "AAOI", "AMD"):
            assert t in tickers, f"NEW position {t} missing from snapshot"
        # 4 EXITED positions must be absent.
        for t in ("MA", "KTOS", "IREN", "AXON"):
            assert t not in tickers, f"EXITED position {t} still in snapshot"

    def test_cash_zero_post_rotation(self):
        snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert snap["cash_eur"] == 0.0


class TestMeliAuthorityUnchanged:
    def test_meli_authoritative_is_thesis_v3(self):
        tr = ThesisReader()
        meli = tr.get_authoritative_version("MELI")
        assert meli is not None
        # The size-change event is NOT a thesis event — it's a sidecar
        # annotation. v3 must remain authoritative.
        assert meli.get("event_type") == "thesis", (
            "MELI authoritative event must remain a `thesis` event "
            "(v3 conditional WATCH), not the size_change annotation."
        )
        assert meli.get("thesis_version") == "v3_post_Q1_2026"

    def test_meli_size_change_event_present(self):
        tr = ThesisReader()
        all_events = tr.get_all_versions("MELI")
        size_change = [
            e for e in all_events
            if e.get("event_type") == "thesis_position_size_change"
        ]
        assert len(size_change) >= 1
        last = size_change[-1]
        assert abs(last["new_shares"] - 1.542564) < 1e-6


class TestCerebroPostRotation:
    def test_axon_not_in_recommendations(self):
        state = gen.generate_cerebro_state(date(2026, 5, 14))
        rec_assets = {r["asset"] for r in state["recommendations"]}
        assert "AXON" not in rec_assets, (
            "AXON must not appear in recommendations once the position "
            "is closed."
        )

    def test_axon_not_in_upcoming_events(self):
        state = gen.generate_cerebro_state(date(2026, 5, 14))
        assert "AXON" not in state["upcoming_events_by_asset"]

    def test_meli_recommendation_present(self):
        state = gen.generate_cerebro_state(date(2026, 5, 14))
        rec_assets = {r["asset"] for r in state["recommendations"]}
        assert "MELI" in rec_assets

    def test_nav_in_state_matches_snapshot(self):
        state = gen.generate_cerebro_state(date(2026, 5, 14))
        nav = state["portfolio_real"]["nav_total_eur"]
        assert 48178 < nav < 48189

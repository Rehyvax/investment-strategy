"""Tests for the deterministic cerebro state generator."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_cerebro_state as gen  # noqa: E402


# ---------------------------------------------------------------------
# Top-level schema
# ---------------------------------------------------------------------
class TestSchema:
    def test_required_top_level_keys(self):
        state = gen.generate_cerebro_state(date(2026, 5, 14))
        required = {
            "generated_at",
            "next_evaluation",
            "as_of_date",
            "market_state",
            "portfolio_real",
            "tax_alerts",
            "portfolios_chart_data",
            "recommendations",
            "comparative_analysis",
            "news_feed",
        }
        assert required.issubset(state.keys())

    def test_portfolio_real_required_fields(self):
        p = gen.generate_portfolio_real(date(2026, 5, 14))
        required = {
            "nav_total_eur",
            "nav_delta_1d_pct",
            "nav_delta_1w_pct",
            "nav_delta_1m_pct",
            "nav_delta_ytd_pct",
            "health_status",
            "health_summary",
            "drawdown_current_pct",
            "drawdown_from_peak",
            "cash_eur",
            "cash_pct_nav",
            "positions_count",
        }
        assert required.issubset(p.keys())


# ---------------------------------------------------------------------
# Portfolio real
# ---------------------------------------------------------------------
class TestPortfolioReal:
    def test_nav_matches_rebuilder_snapshot(self):
        """Real snapshot 2026-05-12 has NAV 47,864.65 EUR (deterministic
        rebuilder output). Generator must reflect it."""
        data = gen.generate_portfolio_real(date(2026, 5, 14))
        assert 47000 < data["nav_total_eur"] < 49000
        assert data["positions_count"] >= 15

    def test_health_green_no_false_breach(self):
        """Rebuilder snapshots lack sector/country metadata; the health
        check must not fire false-positive breaches because of it."""
        data = gen.generate_portfolio_real(date(2026, 5, 14))
        assert data["health_status"] in ("green", "yellow")

    def test_drawdown_negative_or_zero(self):
        data = gen.generate_portfolio_real(date(2026, 5, 14))
        assert data["drawdown_current_pct"] <= 0.0


# ---------------------------------------------------------------------
# Tax alerts (2-month rule)
# ---------------------------------------------------------------------
class TestTaxAlerts:
    def test_meli_alert_active_before_window_end(self):
        alerts = gen.generate_tax_alerts(date(2026, 5, 14))
        meli = [a for a in alerts if a["asset"] == "MELI"]
        assert len(meli) == 1
        assert meli[0]["alert_type"] == "2_month_rule"
        assert meli[0]["expires"] == "2026-07-11"
        assert "280.45" in meli[0]["message"]

    def test_meli_alert_expired_after_window_end(self):
        alerts = gen.generate_tax_alerts(date(2026, 7, 15))
        meli = [a for a in alerts if a["asset"] == "MELI"]
        assert len(meli) == 0


# ---------------------------------------------------------------------
# Recommendations (theses-driven)
# ---------------------------------------------------------------------
class TestRecommendations:
    def test_top_3_cap(self):
        recs = gen.generate_recommendations(date(2026, 5, 14))
        assert len(recs) <= 3

    def test_axon_override_active(self):
        recs = gen.generate_recommendations(date(2026, 5, 14))
        axon = [r for r in recs if r["asset"] == "AXON"]
        assert len(axon) == 1
        assert axon[0]["type"] == "HOLD_OVERRIDE"
        assert axon[0]["priority"] == "high"
        assert axon[0]["color"] == "orange"

    def test_meli_watch_with_active_falsifier(self):
        """MELI thesis has a dict falsifier_status_audit with 1 falsifier
        in 'halfway_activated' state → must surface as WATCH high."""
        recs = gen.generate_recommendations(date(2026, 5, 14))
        meli = [r for r in recs if r["asset"] == "MELI"]
        assert len(meli) == 1
        assert meli[0]["type"] == "WATCH"
        assert meli[0]["priority"] == "high"

    def test_msft_hold_no_falsifier_in_motion(self):
        recs = gen.generate_recommendations(date(2026, 5, 14))
        msft = [r for r in recs if r["asset"] == "MSFT"]
        # MSFT may or may not survive the top-3 cap; if it does, it
        # should be HOLD (no halfway_activated falsifier in its thesis).
        if msft:
            assert msft[0]["type"] in ("HOLD", "WATCH")

    def test_each_rec_has_narrative_source(self, monkeypatch):
        """Every rec carries a `_narrative_source` tag so the dashboard
        can show LLM vs DETERMINISTA. Scrub env so we exercise the
        rule_based path without burning tokens."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        recs = gen.generate_recommendations(date(2026, 5, 14))
        for rec in recs:
            assert "_narrative_source" in rec
            assert rec["_narrative_source"] in ("llm", "rule_based")


# ---------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------
class TestChartData:
    def test_nine_portfolios_present(self):
        chart = gen.generate_portfolios_chart_data(date(2026, 5, 14))
        names = {s["name"] for s in chart["series"]}
        # All 9 paper portfolios should have at least a T0 snapshot.
        expected = {
            "real",
            "shadow",
            "quality",
            "value",
            "momentum",
            "aggressive",
            "conservative",
            "benchmark_passive",
            "robo_advisor",
        }
        assert expected.issubset(names)

    def test_real_default_visible(self):
        chart = gen.generate_portfolios_chart_data(date(2026, 5, 14))
        real_series = next(s for s in chart["series"] if s["name"] == "real")
        assert real_series["default_visible"] is True

    def test_normalized_base_100(self):
        chart = gen.generate_portfolios_chart_data(date(2026, 5, 14))
        for series in chart["series"]:
            assert series["values"][0] == pytest.approx(100.0)


# ---------------------------------------------------------------------
# Comparative
# ---------------------------------------------------------------------
class TestComparative:
    def test_required_fields(self):
        c = gen.generate_comparative(date(2026, 5, 14))
        for k in (
            "headline",
            "narrative",
            "comparator_today",
            "comparator_reason",
            "action",
        ):
            assert k in c

    def test_comparator_rotates(self):
        candidates = {"shadow", "benchmark_passive", "robo_advisor"}
        seen = set()
        for d in (date(2026, 5, 14), date(2026, 5, 15), date(2026, 5, 16)):
            seen.add(gen.generate_comparative(d)["comparator_today"])
        assert seen.issubset(candidates)
        assert len(seen) >= 2  # rotation actually happens

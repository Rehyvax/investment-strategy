"""Tests for `scripts/agents/risk_manager.py`.

The pure helpers (`compute_concentrations`, `parse_risk_response`)
need no I/O. The end-to-end `evaluate_action` test exercises the
no-client fallback so no LLM call is made."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.agents import risk_manager as rm  # noqa: E402


# ---------------------------------------------------------------------------
# compute_concentrations — pure
# ---------------------------------------------------------------------------
class TestComputeConcentrations:
    def test_aggregates_sector_country_and_top(self):
        snap = {
            "nav_total_eur": 100000.0,
            "cash_eur": 5000.0,
            "positions": [
                {
                    "ticker": "MSFT",
                    "weight_pct": 30.0,
                    "sector_at_purchase": "Technology",
                    "country_at_purchase": "United States",
                },
                {
                    "ticker": "AAPL",
                    "weight_pct": 25.0,
                    "sector_at_purchase": "Technology",
                    "country_at_purchase": "United States",
                },
                {
                    "ticker": "ASML",
                    "weight_pct": 15.0,
                    "sector_at_purchase": "Technology",
                    "country_at_purchase": "Netherlands",
                },
                {
                    "ticker": "JNJ",
                    "weight_pct": 25.0,
                    "sector_at_purchase": "Healthcare",
                    "country_at_purchase": "United States",
                },
            ],
        }
        out = rm.compute_concentrations(snap, "MSFT")
        assert out["nav"] == 100000.0
        assert out["cash"] == 5000.0
        assert out["cash_pct"] == 5.0
        assert out["n_positions"] == 4
        assert out["top_position"] == "MSFT"
        assert out["top_pct"] == 30.0
        assert out["current_position_pct"] == 30.0
        # Sectors >10% only.
        assert out["sector_concentrations"]["Technology"] == 70.0
        assert out["sector_concentrations"]["Healthcare"] == 25.0
        # Countries >20%.
        assert out["country_concentrations"]["United States"] == 80.0
        assert "Netherlands" not in out["country_concentrations"]


# ---------------------------------------------------------------------------
# parse_risk_response — defensive
# ---------------------------------------------------------------------------
class TestParseRiskResponse:
    def test_parses_clean_json(self):
        text = (
            '{"approval":"approve","modification":null,'
            '"reasoning":"All caps respected.",'
            '"constraint_check":{"cap_single":"ok","cap_sector":"warning","cash_buffer":"ok"}}\n'
            "Approve: post-trade weight 8%, sector Tech 32%, cash buffer 5%."
        )
        out = rm.parse_risk_response(text)
        assert out["approval"] == "approve"
        assert out["constraint_check"]["cap_sector"] == "warning"
        assert "post-trade weight" in out["reasoning"]

    def test_strips_markdown_fence(self):
        text = (
            "```json\n"
            '{"approval":"reject","reasoning":"Sector breach","constraint_check":{}}\n'
            "```\n"
            "Reject because sector breach."
        )
        out = rm.parse_risk_response(text)
        assert out["approval"] == "reject"

    def test_invalid_json_falls_back_to_modify(self):
        out = rm.parse_risk_response("not json")
        assert out["approval"] == "modify"
        assert out["modification"] == "manual_review_required"
        assert out.get("_parse_error") == "json_decode_failed"

    def test_unknown_approval_falls_back_to_modify(self):
        text = '{"approval":"yolo","constraint_check":{}}\n'
        out = rm.parse_risk_response(text)
        assert out["approval"] == "modify"


# ---------------------------------------------------------------------------
# evaluate_action — no-client fallback
# ---------------------------------------------------------------------------
class TestEvaluateActionNoLLM:
    def test_returns_none_when_client_absent(self, monkeypatch):
        monkeypatch.setattr(rm, "get_client", lambda: None)
        out = rm.evaluate_action(
            {"suggested_action": "reduce", "verdict": "thesis_weakened"},
            {"drawdown_current_pct": -3.0},
            "MSFT",
            snapshot={
                "nav_total_eur": 50000,
                "cash_eur": 2000,
                "positions": [
                    {"ticker": "MSFT", "weight_pct": 8.0,
                     "sector_at_purchase": "Tech",
                     "country_at_purchase": "US"}
                ],
            },
        )
        assert out is None

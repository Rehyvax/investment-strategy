"""Tests for `scripts/agents/claude_autonomous.py` — parsing + degradation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.agents import claude_autonomous as ca  # noqa: E402


# ---------------------------------------------------------------------------
class TestParseDecisionResponse:
    def test_parses_clean_json_with_critique(self):
        text = (
            '{"decision_type":"hold","reasoning_overall":"market is calm",'
            '"trades":[],"rebalance_target":null,"expected_horizon_days":7,'
            '"self_assessed_risk":"low"}\n'
            "Podría estar equivocado si la volatilidad sube."
        )
        out = ca._parse_decision_response(text)
        assert out is not None
        assert out["decision_type"] == "hold"
        assert out["self_critique"].startswith("Podría")

    def test_strips_markdown_fence(self):
        text = (
            "```json\n"
            '{"decision_type":"trade","trades":[{"ticker":"AAPL","action":"buy",'
            '"qty":5,"thesis":"valuation","confidence":"medium",'
            '"exit_trigger":"stop -10%"}]}\n'
            "```\nSelf-critique here."
        )
        out = ca._parse_decision_response(text)
        assert out is not None
        assert out["decision_type"] == "trade"
        assert len(out["trades"]) == 1
        assert out["trades"][0]["ticker"] == "AAPL"

    def test_returns_none_on_no_json(self):
        assert ca._parse_decision_response("just text no json") is None

    def test_handles_braces_in_strings(self):
        text = (
            '{"decision_type":"hold","reasoning_overall":'
            '"market said {something}","trades":[]}'
        )
        out = ca._parse_decision_response(text)
        assert out is not None
        assert out["decision_type"] == "hold"


# ---------------------------------------------------------------------------
class TestPortfolioReturn:
    def test_zero_when_no_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ca, "SNAPSHOTS_DIR", tmp_path)
        assert ca._portfolio_30d_return("missing") == 0.0

    def test_basic_computation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ca, "SNAPSHOTS_DIR", tmp_path)
        from datetime import date, timedelta
        pdir = tmp_path / "claude_autonomous"
        pdir.mkdir()
        for i, mult in enumerate([1.0, 1.05]):  # 5% gain
            d = (date.today() - timedelta(days=10 - i)).isoformat()
            (pdir / f"{d}.json").write_text(
                json.dumps({"nav_total_eur": 50000 * mult}), encoding="utf-8"
            )
        ret = ca._portfolio_30d_return("claude_autonomous")
        assert ret == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
class TestMakeDecisionDegradation:
    def test_returns_none_without_alpaca(self, monkeypatch):
        monkeypatch.setattr(ca, "alpaca_available", lambda: False)
        out = ca.make_autonomous_decision({})
        assert out is None

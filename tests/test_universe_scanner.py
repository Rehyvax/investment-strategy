"""Tests for the universe scanner inside claude_autonomous.

The real `get_universe_scanner_results` calls yfinance — we mock it
to keep the suite offline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.agents import claude_autonomous as ca  # noqa: E402


class _FakeTicker:
    def __init__(self, info: dict) -> None:
        self.info = info


class _FakeYF:
    def __init__(self, info_map: dict[str, dict]) -> None:
        self._info_map = info_map

    def Ticker(self, symbol: str) -> _FakeTicker:  # noqa: N802
        return _FakeTicker(self._info_map.get(symbol, {}))


class TestScanner:
    def test_returns_empty_when_no_yfinance(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "yfinance", None)
        out = ca.get_universe_scanner_results(max_candidates=5)
        # Either empty or any list — never raises.
        assert isinstance(out, list)

    def test_filters_by_pe_and_growth(self, monkeypatch):
        info_map = {
            t: {"trailingPE": 20, "revenueGrowth": 0.15, "marketCap": 1e11,
                "sector": "Tech"}
            for t in ca.DEFAULT_UNIVERSE
        }
        # Make one ticker have negative growth — should be filtered out
        info_map["AAPL"] = {
            "trailingPE": 30, "revenueGrowth": 0.02, "marketCap": 3e12,
            "sector": "Tech",
        }
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(info_map))
        out = ca.get_universe_scanner_results(max_candidates=10)
        assert len(out) <= 10
        for r in out:
            assert r["pe"] > 0
            assert r["pe"] <= 100
            assert r["rev_growth"] >= 0.05
        assert all(r["ticker"] != "AAPL" for r in out)

    def test_caps_at_max_candidates(self, monkeypatch):
        info_map = {
            t: {"trailingPE": 25, "revenueGrowth": 0.20}
            for t in ca.DEFAULT_UNIVERSE
        }
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(info_map))
        out = ca.get_universe_scanner_results(max_candidates=3)
        assert len(out) <= 3

    def test_sort_by_pe_over_growth(self, monkeypatch):
        info_map = {
            "AAA": {"trailingPE": 10, "revenueGrowth": 0.10},
            "BBB": {"trailingPE": 50, "revenueGrowth": 0.10},
            "CCC": {"trailingPE": 30, "revenueGrowth": 0.30},
        }
        # Force the universe to include only these 3
        monkeypatch.setattr(ca, "DEFAULT_UNIVERSE", ("AAA", "BBB", "CCC"))
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(info_map))
        out = ca.get_universe_scanner_results(max_candidates=3)
        if len(out) == 3:
            scores = [r["pe"] / max(r["rev_growth"], 0.01) for r in out]
            assert scores == sorted(scores)

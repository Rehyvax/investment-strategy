"""Tests for `scripts/portfolios/hrp_portfolio.py`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolios import hrp_portfolio as hp  # noqa: E402


class TestEqualWeightFallback:
    def test_empty_tickers(self):
        assert hp._equal_weight([]) == {}

    def test_distributes_evenly(self):
        out = hp._equal_weight(["A", "B", "C", "D"])
        for v in out.values():
            assert v == pytest.approx(0.25, abs=0.001)
        assert sum(out.values()) == pytest.approx(1.0, abs=0.001)


class TestComputeHrpWeightsDegradation:
    def test_empty_tickers_returns_empty(self):
        assert hp.compute_hrp_weights([]) == {}

    def test_no_yfinance_falls_back(self, monkeypatch):
        # Force yfinance import to fail in fallback chain.
        monkeypatch.setitem(sys.modules, "yfinance", None)
        out = hp.compute_hrp_weights(["AAA", "BBB", "CCC"])
        # Without yfinance the inverse-vol path also short-circuits to
        # equal weight.
        assert isinstance(out, dict)
        assert len(out) == 3
        # Equal weights summing to 1.
        for v in out.values():
            assert v == pytest.approx(1 / 3, abs=0.001)


class TestSnapshotSkipWhenEmpty:
    def test_skip_when_real_universe_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hp, "REAL_DIR", tmp_path / "missing_real")
        monkeypatch.setattr(hp, "HRP_DIR", tmp_path / "out")
        out = hp.update_hrp_snapshot()
        assert out is None

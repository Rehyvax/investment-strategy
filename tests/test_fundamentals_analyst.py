"""Tests for `scripts/fundamentals_analyst.py`.

Pure-flag tests run with no I/O. The end-to-end `compute_fundamentals`
test mocks `yfinance.Ticker` so no network call is made.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import fundamentals_analyst as fa  # noqa: E402


# ---------------------------------------------------------------------------
# compute_flags — pure function
# ---------------------------------------------------------------------------
class TestComputeFlags:
    def test_high_pe(self):
        flags = fa.compute_flags({"pe_ratio": 60})
        assert "high_pe" in flags

    def test_low_pe(self):
        flags = fa.compute_flags({"pe_ratio": 7})
        assert "low_pe" in flags

    def test_high_leverage(self):
        flags = fa.compute_flags({"debt_to_equity": 250})
        assert "high_leverage" in flags

    def test_liquidity_concern(self):
        flags = fa.compute_flags({"current_ratio": 0.8})
        assert "liquidity_concern" in flags

    def test_operating_loss(self):
        flags = fa.compute_flags({"operating_margin": -0.05})
        assert "operating_loss" in flags

    def test_strong_revenue_growth(self):
        flags = fa.compute_flags({"revenue_growth": 0.40})
        assert "strong_revenue_growth" in flags

    def test_revenue_decline(self):
        flags = fa.compute_flags({"revenue_growth": -0.10})
        assert "revenue_decline" in flags

    def test_clean_metrics_yield_no_flags(self):
        flags = fa.compute_flags(
            {
                "pe_ratio": 20,
                "debt_to_equity": 50,
                "current_ratio": 2.0,
                "operating_margin": 0.15,
                "revenue_growth": 0.08,
            }
        )
        assert flags == []

    def test_handles_none_values(self):
        # Missing fields should NOT raise nor produce flags.
        flags = fa.compute_flags({})
        assert flags == []


# ---------------------------------------------------------------------------
# compute_fundamentals with mocked yfinance
# ---------------------------------------------------------------------------
class _FakeTicker:
    def __init__(self, info: dict):
        self.info = info


class _FakeYF:
    def __init__(self, info: dict):
        self._info = info

    def Ticker(self, _ticker: str) -> _FakeTicker:  # noqa: N802
        return _FakeTicker(self._info)


class TestComputeFundamentals:
    def test_returns_full_dict_for_valid_info(self, monkeypatch):
        info = {
            "symbol": "MSFT",
            "trailingPE": 32.5,
            "forwardPE": 28.0,
            "operatingMargins": 0.45,
            "revenueGrowth": 0.13,
            "debtToEquity": 30.0,
            "currentRatio": 1.7,
            "sector": "Technology",
            "targetMeanPrice": 450.0,
            "recommendationKey": "buy",
            "marketCap": 3_000_000_000_000,
        }
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(info))
        out = fa.compute_fundamentals("MSFT")
        assert "error" not in out
        assert out["pe_ratio"] == 32.5
        assert out["sector"] == "Technology"
        assert "flags" in out
        # Clean profile → no flags.
        assert out["flags"] == []

    def test_returns_error_on_missing_symbol(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF({}))
        out = fa.compute_fundamentals("BOGUS")
        assert out.get("error") == "no_info"

    def test_handles_partial_data(self, monkeypatch):
        # Only `symbol` + `trailingPE` set, everything else missing.
        # Compute should succeed, fields default to None, flags empty.
        info = {"symbol": "PARTIAL", "trailingPE": 18.0}
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(info))
        out = fa.compute_fundamentals("PARTIAL")
        assert "error" not in out
        assert out["pe_ratio"] == 18.0
        assert out["forward_pe"] is None
        assert out["sector"] is None
        assert out["flags"] == []

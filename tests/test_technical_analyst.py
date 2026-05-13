"""Tests for `scripts/technical_analyst.py`.

Pure-classifier tests run with no I/O. The end-to-end `compute_indicators`
test mocks `yfinance.Ticker` so no network call is made.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import technical_analyst as ta  # noqa: E402


# ---------------------------------------------------------------------------
# Pure classifiers
# ---------------------------------------------------------------------------
class TestClassifyTrend:
    def test_bullish_strong_when_price_above_both_mas(self):
        assert ta.classify_trend(110, 100, 90) == "bullish_strong"

    def test_bearish_strong_when_price_below_both_mas(self):
        assert ta.classify_trend(80, 90, 100) == "bearish_strong"

    def test_bullish_mild_when_only_ma50_present(self):
        assert ta.classify_trend(105, 100, None) == "bullish_mild"

    def test_neutral_when_no_mas(self):
        assert ta.classify_trend(100, None, None) == "neutral"


class TestClassifyRsi:
    def test_overbought_above_70(self):
        assert ta.classify_rsi(75) == "overbought"

    def test_oversold_below_30(self):
        assert ta.classify_rsi(25) == "oversold"

    def test_neutral_band(self):
        assert ta.classify_rsi(50) == "neutral"

    def test_strong_momentum_above_60(self):
        assert ta.classify_rsi(65) == "strong_momentum"


class TestClassifyMacd:
    def test_bullish_cross(self):
        assert ta.classify_macd(0.5, -0.1) == "bullish_cross"

    def test_bearish_cross(self):
        assert ta.classify_macd(-0.4, 0.2) == "bearish_cross"

    def test_bullish_momentum_no_cross(self):
        assert ta.classify_macd(0.3, 0.2) == "bullish_momentum"


# ---------------------------------------------------------------------------
# compute_indicators with mocked yfinance
# ---------------------------------------------------------------------------
class _FakeTicker:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def history(self, **_kwargs) -> pd.DataFrame:
        return self._df


class _FakeYF:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def Ticker(self, _ticker: str) -> _FakeTicker:  # noqa: N802
        return _FakeTicker(self._df)


def _fake_ohlcv(n: int = 250) -> pd.DataFrame:
    """Synthetic price series with a mild uptrend so MA50 < price."""
    rng = np.random.default_rng(seed=42)
    base = 100 + np.cumsum(rng.normal(0.05, 1.0, size=n))
    idx = pd.date_range(end=date.today(), periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": base,
            "High": base + 0.5,
            "Low": base - 0.5,
            "Close": base,
            "Volume": rng.integers(1_000_000, 5_000_000, size=n),
        },
        index=idx,
    )


class TestComputeIndicators:
    def test_returns_full_dict(self, monkeypatch):
        df = _fake_ohlcv(220)
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(df))
        out = ta.compute_indicators("MOCK")
        assert "error" not in out
        for key in (
            "ticker",
            "as_of_date",
            "price",
            "ma50",
            "ma200",
            "rsi14",
            "macd",
            "macd_histogram",
            "bb_upper",
            "bb_lower",
            "trend",
            "rsi_signal",
            "macd_signal",
            "bb_position",
        ):
            assert key in out
        assert out["ticker"] == "MOCK"
        assert out["bars_used"] == 220
        # Trend label is one of the known buckets.
        assert out["trend"] in {
            "bullish_strong",
            "bullish_mild",
            "bearish_mild",
            "bearish_strong",
            "neutral",
        }

    def test_handles_insufficient_data(self, monkeypatch):
        df = _fake_ohlcv(10)
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(df))
        out = ta.compute_indicators("MOCK")
        assert out.get("error") == "insufficient_data"

    def test_handles_empty_data(self, monkeypatch):
        empty = pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"]
        )
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(empty))
        out = ta.compute_indicators("MOCK")
        assert out.get("error") == "insufficient_data"

"""Tests for benchmark snapshot writers — yfinance mocked."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmarks import indexa_benchmark as ix  # noqa: E402
from scripts.benchmarks import spy_benchmark as sb  # noqa: E402


class _FakeTicker:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def history(self, **_kwargs) -> pd.DataFrame:
        return self._df


class _FakeYFSingle:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def Ticker(self, _symbol: str) -> _FakeTicker:  # noqa: N802
        return _FakeTicker(self._df)


def _fake_history(n: int = 5, last_close: float = 500.0) -> pd.DataFrame:
    return pd.DataFrame({"Close": [last_close - 1] * (n - 1) + [last_close]})


# ---------------------------------------------------------------------------
class TestSpyBenchmark:
    def test_writes_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sb, "SPY_DIR", tmp_path)
        monkeypatch.setitem(
            sys.modules, "yfinance", _FakeYFSingle(_fake_history(last_close=500.0))
        )
        out = sb.update_spy_snapshot(force=True)
        assert out is not None
        assert out.exists()
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["portfolio_id"] == "spy_benchmark"
        assert snap["positions"][0]["ticker"] == "SPY"

    def test_idempotent_unless_forced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sb, "SPY_DIR", tmp_path)
        monkeypatch.setitem(
            sys.modules, "yfinance", _FakeYFSingle(_fake_history())
        )
        first = sb.update_spy_snapshot(force=True)
        first_mtime = first.stat().st_mtime
        # Second call without force returns the same path, no rewrite.
        second = sb.update_spy_snapshot()
        assert second == first
        assert second.stat().st_mtime == first_mtime


# ---------------------------------------------------------------------------
class TestIndexaBenchmark:
    def test_writes_snapshot_with_5_etfs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ix, "INDEXA_DIR", tmp_path)
        monkeypatch.setitem(
            sys.modules, "yfinance", _FakeYFSingle(_fake_history(last_close=200.0))
        )
        out = ix.update_indexa_snapshot(force=True)
        assert out is not None
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["portfolio_id"] == "indexa_10_benchmark"
        # All 5 ETFs in composition produced positions.
        tickers = [p["ticker"] for p in snap["positions"]]
        for t in ("VTI", "VEA", "VWO", "VIG", "BND"):
            assert t in tickers
        # Weights sum ≈ 100%
        total_w = sum(p["weight_pct"] for p in snap["positions"])
        assert total_w == pytest.approx(100.0, abs=0.5)

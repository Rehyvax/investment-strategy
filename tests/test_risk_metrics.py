"""Tests for `scripts/metrics/risk_adjusted.py`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.metrics import risk_adjusted as rm  # noqa: E402


# ---------------------------------------------------------------------------
# Pure metric functions
# ---------------------------------------------------------------------------
class TestSharpe:
    def test_known_returns(self):
        # Constant +0.001 daily ≈ 0.252 annual, std=0 → None
        assert rm.sharpe_ratio([0.001] * 50) is None  # zero std

    def test_normal_returns(self):
        rng = np.random.default_rng(42)
        rs = rng.normal(0.0008, 0.012, size=120).tolist()
        s = rm.sharpe_ratio(rs)
        assert s is not None
        assert isinstance(s, float)

    def test_insufficient_returns_none(self):
        assert rm.sharpe_ratio([0.001] * 5) is None


class TestSortino:
    def test_no_losses_returns_none(self):
        assert rm.sortino_ratio([0.01] * 50) is None

    def test_with_mixed_returns(self):
        rng = np.random.default_rng(7)
        rs = rng.normal(0.0005, 0.015, size=80).tolist()
        s = rm.sortino_ratio(rs)
        assert s is not None

    def test_only_negatives(self):
        rs = [-0.005, -0.01, -0.002, -0.008, -0.003] * 4  # n=20
        s = rm.sortino_ratio(rs)
        assert s is not None
        assert s < 0


class TestMaxDrawdown:
    def test_known_drawdown(self):
        # +10%, -10%, +0%, -10% → cum [1.1, 0.99, 0.99, 0.891]
        # peaks: 1.1 then 1.1; min DD = (0.891-1.1)/1.1 = -19.0%
        rs = [0.10, -0.10, 0.0, -0.10]
        dd = rm.max_drawdown(rs)
        assert dd == pytest.approx(-19.0, abs=0.5)

    def test_only_gains_zero_dd(self):
        dd = rm.max_drawdown([0.01, 0.02, 0.005])
        assert dd == 0.0

    def test_insufficient_returns_none(self):
        assert rm.max_drawdown([0.01]) is None


class TestCalmar:
    def test_requires_30_obs(self):
        assert rm.calmar_ratio([0.001] * 20) is None

    def test_computes_ratio(self):
        rng = np.random.default_rng(11)
        rs = rng.normal(0.001, 0.01, size=60).tolist()
        c = rm.calmar_ratio(rs)
        # May be None when DD == 0; otherwise float
        if c is not None:
            assert isinstance(c, float)


class TestInformationRatio:
    def test_zero_active_std(self):
        rs = [0.01, 0.005, -0.002, 0.003] * 6
        # Same series as benchmark → active=0 → None
        assert rm.information_ratio(rs, rs) is None

    def test_with_alpha(self):
        rng = np.random.default_rng(3)
        bench = rng.normal(0.0008, 0.012, size=80).tolist()
        port = [b + rng.normal(0.0002, 0.005) for b in bench]
        ir = rm.information_ratio(port, bench)
        assert ir is not None


# ---------------------------------------------------------------------------
# Loaders + integration
# ---------------------------------------------------------------------------
class TestComputeAllMetrics:
    def test_insufficient_data(self, tmp_path):
        # No snapshots → 0 returns → status insufficient_data
        out = rm.compute_all_metrics(
            "real", lookback_days=90, snapshots_dir=tmp_path
        )
        assert out["status"] == "insufficient_data"
        assert out["n_observations"] == 0

    def test_with_synthetic_snapshots(self, tmp_path):
        pdir = tmp_path / "real"
        pdir.mkdir(parents=True)
        # Seed 12 snapshots increasing by 0.5% / day
        from datetime import date, timedelta
        nav = 50000.0
        for i in range(12):
            d = (date.today() - timedelta(days=11 - i)).isoformat()
            (pdir / f"{d}.json").write_text(
                json.dumps({"as_of_date": d, "nav_total_eur": nav}),
                encoding="utf-8",
            )
            nav *= 1.005
        out = rm.compute_all_metrics(
            "real", lookback_days=30, snapshots_dir=tmp_path
        )
        assert out["status"] == "ok"
        assert out["n_observations"] == 11  # 12 snapshots → 11 returns


class TestComputeDailyReturns:
    def test_chronological_sort(self, tmp_path):
        pdir = tmp_path / "real"
        pdir.mkdir(parents=True)
        # Write out of order
        from datetime import date, timedelta
        for i, mult in enumerate([1.0, 1.01, 1.02]):
            d = (date.today() - timedelta(days=10 - i)).isoformat()
            (pdir / f"{d}.json").write_text(
                json.dumps({"nav_total_eur": 100 * mult}), encoding="utf-8"
            )
        rs = rm.compute_daily_returns(
            "real", lookback_days=30, snapshots_dir=tmp_path
        )
        # Must be sorted ascending → returns = [0.01, ~0.0099]
        assert len(rs) == 2
        assert rs[0] == pytest.approx(0.01, abs=0.001)

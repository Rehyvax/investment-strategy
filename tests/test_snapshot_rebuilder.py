"""Pre-anchored tests for SnapshotRebuilder.

Tolerances:
- real, shadow: ±€10 vs rebuilder-deterministic NAV (price log canonical).
- quality, value: exact (50,000.00 EUR all-cash after supersessions).
- benchmark_passive: idempotency within ±2% across consecutive days.

Note: post-2026-05-14, expected NAVs reflect the deterministic
rebuilder + price log convention. Pre-rebuilder fixtures (NAV 48,605.45
real / 49,842.55 shadow) used inconsistent per-portfolio FX and mixed
price sources; archived under data/snapshots/_archive/.
"""

from datetime import date

import pytest

from src.portfolios.snapshot import SnapshotRebuilder


class TestSnapshotRebuilder:
    def test_real_2026_05_12(self):
        """real: 5 day-trades + reconciliation override; deterministic price log."""
        rb = SnapshotRebuilder("real", date(2026, 5, 12), dry_run=True)
        snapshot = rb.rebuild().to_dict()
        expected_nav = 47864.65
        assert abs(snapshot["nav_total_eur"] - expected_nav) < 10, (
            f"NAV {snapshot['nav_total_eur']} vs expected {expected_nav} "
            f"diff {snapshot['nav_total_eur'] - expected_nav}"
        )
        assert snapshot["positions_count"] == 19

    def test_quality_2026_05_13(self):
        """quality: all 19 trades (v1+v2) superseded via 2 deployment_unwind events → 50k cash."""
        rb = SnapshotRebuilder("quality", date(2026, 5, 13), dry_run=True)
        snapshot = rb.rebuild().to_dict()
        assert abs(snapshot["nav_total_eur"] - 50000.00) < 1
        assert snapshot["positions_count"] == 0
        assert abs(snapshot["cash_eur"] - 50000.00) < 1

    def test_value_2026_05_13(self):
        """value: 15 v1 trades superseded → 50k cash, 0 positions."""
        rb = SnapshotRebuilder("value", date(2026, 5, 13), dry_run=True)
        snapshot = rb.rebuild().to_dict()
        assert abs(snapshot["nav_total_eur"] - 50000.00) < 1
        assert snapshot["positions_count"] == 0

    def test_shadow_2026_05_12(self):
        """shadow: 20 BUYs, no supersession; deterministic price log."""
        rb = SnapshotRebuilder("shadow", date(2026, 5, 12), dry_run=True)
        snapshot = rb.rebuild().to_dict()
        expected_nav = 49284.55
        assert abs(snapshot["nav_total_eur"] - expected_nav) < 10, (
            f"NAV {snapshot['nav_total_eur']} vs expected {expected_nav}"
        )
        assert snapshot["positions_count"] == 20

    def test_benchmark_passive_idempotent(self):
        """benchmark_passive: no trades since T0; NAV moves only by mark-to-market drift."""
        rb1 = SnapshotRebuilder("benchmark_passive", date(2026, 5, 11), dry_run=True)
        rb2 = SnapshotRebuilder("benchmark_passive", date(2026, 5, 12), dry_run=True)
        s1 = rb1.rebuild().to_dict()
        s2 = rb2.rebuild().to_dict()
        drift = abs(s1["nav_total_eur"] - s2["nav_total_eur"]) / s1["nav_total_eur"]
        assert drift < 0.02, f"drift {drift:.4%} between 2026-05-11 and 2026-05-12"
        assert s1["positions_count"] == s2["positions_count"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

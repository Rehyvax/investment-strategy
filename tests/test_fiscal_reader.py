"""Tests for `dashboard/services/fiscal_reader.py`."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))

from services.fiscal_reader import FiscalReader, _estimate_irpf  # noqa: E402


def _seed(
    tmp_path: Path,
    *,
    sells: list[dict] | None = None,
    buys: list[dict] | None = None,
    snapshot_positions: list[dict] | None = None,
) -> FiscalReader:
    sells = sells or []
    buys = buys or []
    trades = [
        {"event_type": "trade", "side": "sell", **s} for s in sells
    ] + [{"event_type": "trade", "side": "buy", **b} for b in buys]
    trades_fp = tmp_path / "trades.jsonl"
    trades_fp.write_text(
        "\n".join(json.dumps(t) for t in trades) + "\n", encoding="utf-8"
    )

    snaps_dir = tmp_path / "real"
    snaps_dir.mkdir(parents=True, exist_ok=True)
    snap = {
        "as_of_date": "2026-11-15",
        "nav_total_eur": 50000.0,
        "cash_eur": 1000.0,
        "positions": snapshot_positions or [],
    }
    (snaps_dir / "2026-11-15.json").write_text(json.dumps(snap), encoding="utf-8")

    return FiscalReader(trades_fp=trades_fp, snapshots_dir=snaps_dir)


# ---------------------------------------------------------------------------
class TestRealizedPnlBreakdown:
    def test_breakdown_separates_gains_losses(self, tmp_path):
        r = _seed(
            tmp_path,
            sells=[
                {
                    "ticker": "A",
                    "trade_date": "2026-03-10",
                    "realized_pnl_eur": 200.0,
                    "is_loss": False,
                },
                {
                    "ticker": "B",
                    "trade_date": "2026-04-05",
                    "realized_pnl_eur": -80.0,
                    "is_loss": True,
                },
                {
                    "ticker": "C",
                    "trade_date": "2025-12-01",
                    "realized_pnl_eur": 999.0,
                },
            ],
        )
        out = r.get_realized_pnl_breakdown(2026)
        assert out["gains_eur"] == 200.0
        assert out["losses_eur"] == -80.0
        assert out["net_eur"] == 120.0
        assert out["n_gains"] == 1
        assert out["n_losses"] == 1
        # 120 EUR fully inside the 19% bracket
        assert out["estimated_irpf_eur"] == pytest.approx(22.8, abs=0.01)

    def test_irpf_brackets_pure(self):
        # Just under 6k: 19% only
        assert _estimate_irpf(5000.0) == pytest.approx(950.0, abs=0.01)
        # Cross 6k: 6000*0.19 + 4000*0.21 = 1140 + 840 = 1980
        assert _estimate_irpf(10000.0) == pytest.approx(1980.0, abs=0.01)

    def test_loss_carryforward_when_net_negative(self, tmp_path):
        r = _seed(
            tmp_path,
            sells=[
                {
                    "ticker": "X",
                    "trade_date": "2026-02-01",
                    "realized_pnl_eur": -300.0,
                    "is_loss": True,
                }
            ],
        )
        out = r.get_realized_pnl_breakdown(2026)
        assert out["net_eur"] == -300.0
        assert out["loss_carryforward_available_eur"] == -300.0
        assert out["estimated_irpf_eur"] == 0.0


# ---------------------------------------------------------------------------
class TestTwoMonthLocks:
    def test_active_lock_with_no_repurchase(self, tmp_path):
        r = _seed(
            tmp_path,
            sells=[
                {
                    "ticker": "MELI",
                    "isin": "US58733R1023",
                    "trade_date": "2026-05-12",
                    "realized_pnl_eur": -280.45,
                    "is_loss": True,
                    "two_month_rule_window_end": "2026-07-11",
                }
            ],
        )
        locks = r.get_active_two_month_locks(as_of=date(2026, 5, 14))
        assert len(locks) == 1
        assert locks[0]["ticker"] == "MELI"
        assert locks[0]["loss_eur"] == 280.45
        assert locks[0]["repurchase_detected"] is False
        assert locks[0]["days_remaining"] == 58

    def test_lock_detects_repurchase(self, tmp_path):
        r = _seed(
            tmp_path,
            sells=[
                {
                    "ticker": "MELI",
                    "isin": "US58733R1023",
                    "trade_date": "2026-05-12",
                    "realized_pnl_eur": -280.45,
                    "is_loss": True,
                    "two_month_rule_window_end": "2026-07-11",
                }
            ],
            buys=[
                {
                    "ticker": "MELI",
                    "isin": "US58733R1023",
                    "trade_date": "2026-06-01",
                    "quantity": 1.0,
                    "event_id": "01BUY",
                }
            ],
        )
        locks = r.get_active_two_month_locks(as_of=date(2026, 6, 5))
        assert len(locks) == 1
        assert locks[0]["repurchase_detected"] is True
        assert locks[0]["repurchase_detail"]["trade_date"] == "2026-06-01"


# ---------------------------------------------------------------------------
class TestFifoLogAndExport:
    def test_fifo_log_pro_rates_lots(self, tmp_path):
        r = _seed(
            tmp_path,
            sells=[
                {
                    "ticker": "MSFT",
                    "isin": "US5949181045",
                    "trade_date": "2026-05-12",
                    "quantity": 4.0,
                    "price_native": 410.0,
                    "proceeds_eur": 1400.0,
                    "realized_pnl_eur": 100.0,
                    "is_loss": False,
                    "fifo_consumption": [
                        {
                            "lot_id": "L1",
                            "quantity": 3.0,
                            "cost_basis_eur": 900.0,
                        },
                        {
                            "lot_id": "L2",
                            "quantity": 1.0,
                            "cost_basis_eur": 300.0,
                        },
                    ],
                }
            ],
        )
        log = r.get_fifo_log(2026)
        assert len(log) == 2
        # Pro-rate: 100 * 3/4 = 75 for L1, 100 * 1/4 = 25 for L2
        l1 = next(r for r in log if r["lot_id"] == "L1")
        l2 = next(r for r in log if r["lot_id"] == "L2")
        assert l1["realized_pnl_eur_lot"] == pytest.approx(75.0, abs=0.01)
        assert l2["realized_pnl_eur_lot"] == pytest.approx(25.0, abs=0.01)

        csv = r.export_fifo_csv(2026)
        assert "Fecha venta" in csv  # header
        assert "MSFT" in csv
        assert "L1" in csv


# ---------------------------------------------------------------------------
class TestHarvestingCandidates:
    def test_only_q4_returns_candidates(self, tmp_path):
        r = _seed(
            tmp_path,
            snapshot_positions=[
                {
                    "ticker": "X",
                    "isin": "US0000000001",
                    "cost_basis_per_share_native": 100.0,
                    "current_price_native": 80.0,  # -20%
                    "current_value_eur": 800.0,
                    "unrealized_pnl_eur": -200.0,
                }
            ],
        )
        # In Q4 (e.g. 2026-11-15) — should return candidate
        out = r.get_tax_loss_harvesting_candidates(as_of=date(2026, 11, 15))
        assert len(out) == 1
        assert out[0]["ticker"] == "X"
        assert out[0]["unrealized_pnl_pct"] == pytest.approx(-20.0, abs=0.01)
        # Outside Q4 (e.g. May) — should return empty
        out_may = r.get_tax_loss_harvesting_candidates(as_of=date(2026, 5, 15))
        assert out_may == []

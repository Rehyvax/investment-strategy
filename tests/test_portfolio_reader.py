"""Tests for `dashboard/services/portfolio_reader.py`."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))

from services.portfolio_reader import (  # noqa: E402
    CAP_SECTOR_PCT,
    CAP_SINGLE_NAME_PCT,
    PortfolioReader,
    _classify_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _seed_snapshot(tmp_path: Path, *, with_sector_data: bool = True) -> Path:
    snap = {
        "as_of_date": "2026-05-14",
        "nav_total_eur": 50000.0,
        "cash_eur": 1000.0,
        "positions": [
            {
                "ticker": "MSFT",
                "isin": "US5949181045",
                "exchange": "NASDAQ",
                "currency": "USD",
                "sector_at_purchase": "Technology" if with_sector_data else None,
                "country_at_purchase": "United States" if with_sector_data else None,
                "quantity": 10.0,
                "cost_basis_per_share_native": 400.0,
                "current_price_native": 420.0,
                "cost_basis_eur": 3500.0,
                "current_value_eur": 4000.0,
                "unrealized_pnl_eur": 500.0,
            },
            {
                "ticker": "MELI",
                "isin": "US58733R1023",
                "exchange": "NASDAQ",
                "currency": "USD",
                "sector_at_purchase": "Consumer" if with_sector_data else None,
                "country_at_purchase": "Argentina" if with_sector_data else None,
                "quantity": 2.0,
                "cost_basis_per_share_native": 1500.0,
                "current_price_native": 1400.0,
                "cost_basis_eur": 2700.0,
                "current_value_eur": 2500.0,
                "unrealized_pnl_eur": -200.0,
            },
        ],
    }
    pdir = tmp_path / "real"
    pdir.mkdir(parents=True, exist_ok=True)
    f = pdir / "2026-05-14.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    return f


def _seed_trades(tmp_path: Path, year: int = 2026) -> Path:
    trades = [
        # current year — gain
        {
            "event_type": "trade",
            "side": "sell",
            "ticker": "AAPL",
            "trade_date": f"{year}-03-10",
            "realized_pnl_eur": 100.0,
            "is_loss": False,
        },
        # current year — loss
        {
            "event_type": "trade",
            "side": "sell",
            "ticker": "MELI",
            "trade_date": f"{year}-04-15",
            "realized_pnl_eur": -50.0,
            "is_loss": True,
            "two_month_rule_window_end": f"{year}-06-14",
        },
        # previous year — should be filtered out
        {
            "event_type": "trade",
            "side": "sell",
            "ticker": "TSLA",
            "trade_date": f"{year - 1}-12-30",
            "realized_pnl_eur": 999.0,
        },
    ]
    f = tmp_path / "trades.jsonl"
    f.write_text(
        "\n".join(json.dumps(t) for t in trades) + "\n", encoding="utf-8"
    )
    return f


def _make_reader(tmp_path: Path, **kwargs) -> PortfolioReader:
    snap = _seed_snapshot(tmp_path, **kwargs)
    trades = _seed_trades(tmp_path)
    cerebro = tmp_path / "cerebro_state.json"
    cerebro.write_text(json.dumps({"debates_by_asset": {}}), encoding="utf-8")
    return PortfolioReader(
        snapshots_dir=tmp_path,
        trades_fp=trades,
        cerebro_state_fp=cerebro,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestEnrichedPositions:
    def test_get_latest_snapshot_returns_enriched(self, tmp_path):
        r = _make_reader(tmp_path)
        positions = r.get_enriched_positions()
        assert len(positions) == 2
        msft = next(p for p in positions if p["ticker"] == "MSFT")
        assert msft["weight_pct"] == pytest.approx(8.0, abs=0.01)  # 4000 / 50000
        assert msft["unrealized_pnl_pct"] == pytest.approx(5.0, abs=0.01)
        assert msft["debate_verdict"] == "no_debate"


class TestKpis:
    def test_get_kpis_computes_correctly(self, tmp_path):
        r = _make_reader(tmp_path)
        kpis = r.get_kpis()
        assert kpis["nav_total_eur"] == 50000.0
        assert kpis["cash_eur"] == 1000.0
        assert kpis["n_positions"] == 2
        assert kpis["unrealized_pnl_eur"] == pytest.approx(300.0, abs=0.01)
        assert kpis["realized_pnl_ytd_eur"] == pytest.approx(50.0, abs=0.01)

    def test_kpi_with_cash_zero(self, tmp_path):
        r = _make_reader(tmp_path)
        # Override snapshot with cash=0
        snap_path = tmp_path / "real" / "2026-05-14.json"
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        data["cash_eur"] = 0.0
        snap_path.write_text(json.dumps(data), encoding="utf-8")
        kpis = r.get_kpis()
        assert kpis["cash_eur"] == 0.0
        assert kpis["cash_pct_nav"] == 0.0


class TestConcentrations:
    def test_get_concentrations_flags_breaches(self, tmp_path):
        r = _make_reader(tmp_path)
        # Force one position above the 12% single cap
        snap_path = tmp_path / "real" / "2026-05-14.json"
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        data["positions"][0]["current_value_eur"] = 10000.0  # 20% of NAV 50k
        data["nav_total_eur"] = 50000.0
        snap_path.write_text(json.dumps(data), encoding="utf-8")

        conc = r.get_concentrations()
        assert any(b.startswith("single_name") for b in conc["breaches"])
        msft_row = next(
            r2 for r2 in conc["single_name"] if r2["ticker"] == "MSFT"
        )
        assert msft_row["status"] == "breach"

    def test_concentration_halfway_warning(self):
        # Pure helper test — single-name 11% triggers 'warn' (>85% of 12%)
        assert _classify_status(11.0, CAP_SINGLE_NAME_PCT) == "warn"
        assert _classify_status(12.5, CAP_SINGLE_NAME_PCT) == "breach"
        assert _classify_status(8.0, CAP_SINGLE_NAME_PCT) == "ok"


class TestRealizedPnl:
    def test_get_realized_pnl_ytd_filters_by_year(self, tmp_path):
        r = _make_reader(tmp_path)
        ytd = r.get_realized_pnl_ytd(year=2026)
        # 100 + (-50) = 50, ignoring the 2025 +999 entry
        assert ytd == pytest.approx(50.0, abs=0.01)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_handles_no_snapshot(self, tmp_path):
        r = PortfolioReader(
            snapshots_dir=tmp_path / "missing",
            trades_fp=tmp_path / "missing.jsonl",
            cerebro_state_fp=tmp_path / "cerebro.json",
            sanitized_real_fp=tmp_path / "missing_sanitized.json",
        )
        kpis = r.get_kpis()
        assert kpis["nav_total_eur"] == 0.0
        assert kpis["n_positions"] == 0
        assert r.get_enriched_positions() == []
        conc = r.get_concentrations()
        assert conc["breaches"] == []

    def test_handles_no_trades(self, tmp_path):
        snap = _seed_snapshot(tmp_path)
        cerebro = tmp_path / "cerebro_state.json"
        cerebro.write_text("{}", encoding="utf-8")
        r = PortfolioReader(
            snapshots_dir=tmp_path,
            trades_fp=tmp_path / "no_trades.jsonl",
            cerebro_state_fp=cerebro,
        )
        ytd = r.get_realized_pnl_ytd()
        assert ytd == 0.0

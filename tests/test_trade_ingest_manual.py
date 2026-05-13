"""Tests for `scripts/trade_ingest.py` (manual-only ingest).

The CSV parser is intentionally NOT covered — it doesn't exist yet
(deferred until a real Lightyear export sample is available)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import trade_ingest as ti  # noqa: E402


# ---------------------------------------------------------------------
# build_manual_trade — derives EUR + net values
# ---------------------------------------------------------------------
class TestBuildManualTrade:
    def test_buy_derives_net_value_with_fees_added(self):
        t = ti.build_manual_trade(
            side="buy",
            trade_date="2026-05-14",
            ticker="aaoi",
            isin="us00253x1028",
            exchange="nasdaq",
            currency="usd",
            quantity=10.0,
            price_native=200.0,
            fees_native=2.0,
            fx_rate_usd_per_eur=1.1738,
        )
        assert t.ticker == "AAOI"
        assert t.isin == "US00253X1028"
        assert t.exchange == "NASDAQ"
        assert t.currency == "USD"
        assert t.gross_value_native == pytest.approx(2000.0)
        assert t.net_value_native == pytest.approx(2002.0)  # buy: gross + fees
        # 2002 / 1.1738 ~ 1705.57
        assert t.net_value_eur == pytest.approx(1705.5716, abs=0.01)

    def test_sell_derives_net_value_with_fees_subtracted(self):
        t = ti.build_manual_trade(
            side="sell",
            trade_date="2026-05-14",
            ticker="MELI",
            isin="US58733R1023",
            exchange="NASDAQ",
            currency="USD",
            quantity=1.0,
            price_native=1500.0,
            fees_native=3.0,
            fx_rate_usd_per_eur=1.1738,
        )
        assert t.gross_value_native == pytest.approx(1500.0)
        assert t.net_value_native == pytest.approx(1497.0)  # sell: gross - fees

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError):
            ti.build_manual_trade(
                side="hodl",  # type: ignore[arg-type]
                trade_date="2026-05-14",
                ticker="X",
                isin="X",
                exchange="X",
                currency="USD",
                quantity=1,
                price_native=1,
                fees_native=0,
                fx_rate_usd_per_eur=1,
            )

    def test_zero_quantity_raises(self):
        with pytest.raises(ValueError):
            ti.build_manual_trade(
                side="buy",
                trade_date="2026-05-14",
                ticker="X",
                isin="X",
                exchange="X",
                currency="USD",
                quantity=0,
                price_native=1,
                fees_native=0,
                fx_rate_usd_per_eur=1,
            )


# ---------------------------------------------------------------------
# check_compliance — three blocking checks
# ---------------------------------------------------------------------
class TestComplianceChecks:
    def _snap(self, **overrides):
        base = {
            "as_of_date": "2026-05-14",
            "nav_total_eur": 50000.0,
            "cash_eur": 5000.0,
            "positions": [
                {
                    "ticker": "MELI",
                    "isin": "US58733R1023",
                    "quantity": 2.0,
                    "current_value_eur": 4000.0,
                },
                {
                    "ticker": "MSFT",
                    "isin": "US5949181045",
                    "quantity": 10.0,
                    "current_value_eur": 4000.0,
                },
            ],
        }
        base.update(overrides)
        return base

    def test_buy_blocks_when_cash_insufficient(self):
        t = ti.build_manual_trade(
            side="buy",
            trade_date="2026-05-14",
            ticker="NVDA",
            isin="US67066G1040",
            exchange="NASDAQ",
            currency="USD",
            quantity=10.0,
            price_native=1000.0,  # gross 10,000 USD ~ 8520 EUR > 5000 cash
            fees_native=0.0,
            fx_rate_usd_per_eur=1.1738,
        )
        payload = ti.check_compliance(
            t, current_snapshot=self._snap(), recent_trades=[]
        )
        assert payload.blocked
        codes = [f.code for f in payload.findings]
        assert "cash_sufficient" in codes
        cash_finding = next(
            f for f in payload.findings if f.code == "cash_sufficient"
        )
        assert cash_finding.severity == "block"

    def test_sell_blocks_when_shares_insufficient(self):
        t = ti.build_manual_trade(
            side="sell",
            trade_date="2026-05-14",
            ticker="MELI",
            isin="US58733R1023",
            exchange="NASDAQ",
            currency="USD",
            quantity=10.0,  # but only 2 held
            price_native=1500.0,
            fees_native=0.0,
            fx_rate_usd_per_eur=1.1738,
        )
        payload = ti.check_compliance(
            t, current_snapshot=self._snap(), recent_trades=[]
        )
        assert payload.blocked
        codes = [f.code for f in payload.findings]
        assert "shares_sufficient" in codes

    def test_cap_single_name_blocks_above_12pct(self):
        # MELI already at 4000 / 50000 = 8% NAV. Add 5000 EUR to push it
        # above 12%: target 6500 EUR -> ~76 USD * 1000 - actually compute
        # from desired EUR addition: 5000 EUR at FX 1.1738 = 5869 USD.
        # Use 1 share at $5869 to force the cap breach cleanly.
        t = ti.build_manual_trade(
            side="buy",
            trade_date="2026-05-14",
            ticker="MELI",
            isin="US58733R1023",
            exchange="NASDAQ",
            currency="USD",
            quantity=1.0,
            price_native=5869.0,
            fees_native=0.0,
            fx_rate_usd_per_eur=1.1738,
        )
        # Snapshot has cash 50000 to isolate the cap test from cash check.
        snap = self._snap(cash_eur=50000.0)
        payload = ti.check_compliance(
            t, current_snapshot=snap, recent_trades=[]
        )
        codes = [f.code for f in payload.findings]
        assert "cap_single_name" in codes
        cap_finding = next(
            f for f in payload.findings if f.code == "cap_single_name"
        )
        assert cap_finding.severity == "block"
        assert payload.blocked

    def test_two_month_rule_blocks_buy_after_recent_loss(self):
        recent_sell = {
            "event_type": "trade",
            "side": "sell",
            "isin": "US58733R1023",
            "is_loss": True,
            "trade_date": "2026-04-20",
            "two_month_rule_window_end": "2026-06-19",
            "realized_pnl_eur": -250.0,
            "event_id": "01XYZ",
        }
        t = ti.build_manual_trade(
            side="buy",
            trade_date="2026-05-14",
            ticker="MELI",
            isin="US58733R1023",
            exchange="NASDAQ",
            currency="USD",
            quantity=1.0,
            price_native=1500.0,
            fees_native=0.0,
            fx_rate_usd_per_eur=1.1738,
        )
        payload = ti.check_compliance(
            t,
            current_snapshot=self._snap(cash_eur=50000.0),
            recent_trades=[recent_sell],
            as_of_date=date(2026, 5, 14),
        )
        codes = [f.code for f in payload.findings]
        assert "two_month_rule" in codes
        twomr = next(f for f in payload.findings if f.code == "two_month_rule")
        assert twomr.severity == "block"
        assert payload.blocked

    def test_compliance_passes_clean_buy(self):
        t = ti.build_manual_trade(
            side="buy",
            trade_date="2026-05-14",
            ticker="VICR",
            isin="US9261433086",
            exchange="NASDAQ",
            currency="USD",
            quantity=1.0,
            price_native=300.0,  # gross ~256 EUR << 5000 cash
            fees_native=1.0,
            fx_rate_usd_per_eur=1.1738,
        )
        payload = ti.check_compliance(
            t, current_snapshot=self._snap(), recent_trades=[]
        )
        assert not payload.blocked


# ---------------------------------------------------------------------
# persist_trade — atomic append
# ---------------------------------------------------------------------
class TestPersistTrade:
    def test_persist_appends_event_with_event_id(self, tmp_path, monkeypatch):
        fake_trades = tmp_path / "trades.jsonl"
        monkeypatch.setattr(ti, "TRADES_FP", fake_trades)
        # Seed with an existing line to verify append-not-overwrite.
        fake_trades.write_text(
            json.dumps({"event_type": "trade", "marker": "pre"}) + "\n",
            encoding="utf-8",
        )
        t = ti.build_manual_trade(
            side="buy",
            trade_date="2026-05-14",
            ticker="VICR",
            isin="US9261433086",
            exchange="NASDAQ",
            currency="USD",
            quantity=1.0,
            price_native=300.0,
            fees_native=1.0,
            fx_rate_usd_per_eur=1.1738,
        )
        event_id = ti.persist_trade(t, as_of_date=date(2026, 5, 14))
        assert isinstance(event_id, str) and len(event_id) == 26

        lines = [
            json.loads(line)
            for line in fake_trades.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 2
        assert lines[0]["marker"] == "pre"
        assert lines[1]["event_id"] == event_id
        assert lines[1]["ticker"] == "VICR"
        assert lines[1]["side"] == "buy"
        assert lines[1]["ingest_source"] == "manual_form_pantalla_7"

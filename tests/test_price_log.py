"""Tests for the price log: append/idempotency/stale_fallback/FX."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.portfolios.price_log import (
    EXCHANGE_SUFFIX,
    PriceFetcher,
    PriceLog,
    derive_yf_symbol,
)


@pytest.fixture
def tmp_log(tmp_path: Path) -> PriceLog:
    return PriceLog(log_dir=tmp_path)


class TestPriceLog:
    def test_append_and_get_exact(self, tmp_log: PriceLog):
        ev = {
            "event_type": "price_eod",
            "ts": "2026-05-12T22:00:00Z",
            "ticker": "MSFT",
            "currency": "USD",
            "close": 408.21,
            "previous_close": 409.30,
            "intraday_pct": -0.00266,
            "source": "yfinance",
            "as_of_date": "2026-05-12",
        }
        assert tmp_log.append_price(ev) is True
        rec = tmp_log.get_price("MSFT", date(2026, 5, 12))
        assert rec is not None
        assert rec.close == pytest.approx(408.21)
        assert rec.data_quality == "exact"
        assert rec.currency == "USD"

    def test_idempotency(self, tmp_log: PriceLog):
        ev = {
            "event_type": "price_eod",
            "ts": "2026-05-12T22:00:00Z",
            "ticker": "MSFT",
            "currency": "USD",
            "close": 408.21,
            "source": "yfinance",
            "as_of_date": "2026-05-12",
        }
        assert tmp_log.append_price(ev) is True
        # Second append with same (ticker, date, source) is skipped.
        assert tmp_log.append_price(ev) is False

    def test_stale_fallback(self, tmp_log: PriceLog):
        # Log holds 2026-05-11 only; query 2026-05-12 returns 2026-05-11.
        tmp_log.append_price(
            {
                "event_type": "price_eod",
                "ts": "2026-05-11T22:00:00Z",
                "ticker": "CRM",
                "currency": "USD",
                "close": 178.27,
                "source": "yfinance",
                "as_of_date": "2026-05-11",
            }
        )
        rec = tmp_log.get_price("CRM", date(2026, 5, 12))
        assert rec is not None
        assert rec.close == pytest.approx(178.27)
        assert rec.data_quality == "stale_fallback"
        assert rec.as_of_date == "2026-05-11"

    def test_get_price_missing(self, tmp_log: PriceLog):
        assert tmp_log.get_price("NOPE", date(2026, 5, 12)) is None

    def test_fx_append_and_get(self, tmp_log: PriceLog):
        ev = {
            "event_type": "fx_eod",
            "ts": "2026-05-12T22:00:00Z",
            "as_of_date": "2026-05-12",
            "native_currency": "USD",
            "native_per_eur": 1.1738,
            "source": "yfinance",
            "fetched_ts": "2026-05-14T10:00:00Z",
        }
        assert tmp_log.append_fx(ev) is True
        rec = tmp_log.get_fx("USD", date(2026, 5, 12))
        assert rec is not None
        assert rec.native_per_eur == pytest.approx(1.1738)
        assert rec.data_quality == "exact"

    def test_fx_eur_identity(self, tmp_log: PriceLog):
        rec = tmp_log.get_fx("EUR", date(2026, 5, 12))
        assert rec is not None
        assert rec.native_per_eur == 1.0
        assert rec.source == "identity"

    def test_list_tickers(self, tmp_log: PriceLog):
        for t in ("AAA", "BBB", "AAA"):
            tmp_log.append_price(
                {
                    "event_type": "price_eod",
                    "ts": "2026-05-11T22:00:00Z",
                    "ticker": t,
                    "currency": "USD",
                    "close": 100.0,
                    "source": "yfinance",
                    "as_of_date": "2026-05-11",
                }
            )
        assert tmp_log.list_tickers() == {"AAA", "BBB"}


class TestPriceLogDeriveSymbol:
    def test_us_ticker_passthrough(self):
        assert derive_yf_symbol("MSFT", "NASDAQ") == "MSFT"
        assert derive_yf_symbol("CRM", None) == "CRM"

    def test_european_exchange_suffix(self):
        assert derive_yf_symbol("ASML", "Euronext_AMS") == "ASML.AS"
        assert derive_yf_symbol("EUNH", "XETRA") == "EUNH.DE"
        assert derive_yf_symbol("SHEL", "LSE") == "SHEL.L"
        assert derive_yf_symbol("OR", "Euronext_PAR") == "OR.PA"

    def test_double_suffix_avoided(self):
        # If caller already passed the suffixed form, don't append again.
        assert derive_yf_symbol("ASML.AS", "Euronext_AMS") == "ASML.AS"


class TestPriceFetcherOffline:
    """Tests that don't require network — verify symbol resolution etc."""

    def test_known_exchanges_in_map(self):
        # Sanity: spec-required exchanges are mapped.
        for ex in ("XETRA", "LSE", "Euronext_AMS", "Copenhagen_OMX", "BME"):
            assert ex in EXCHANGE_SUFFIX

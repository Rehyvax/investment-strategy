"""Tests for `scripts/alpaca/client.py` — pure / no-network paths."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.alpaca import client as ac  # noqa: E402


# ---------------------------------------------------------------------------
class TestNoCredentials:
    def test_alpaca_available_false_without_keys(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
        assert ac.alpaca_available() is False

    def test_get_trading_client_returns_none(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
        assert ac.get_trading_client() is None

    def test_get_account_summary_returns_none(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
        assert ac.get_account_summary() is None

    def test_get_positions_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
        assert ac.get_positions() == []


# ---------------------------------------------------------------------------
class TestPlaceMarketOrderValidation:
    def test_invalid_side_returns_none(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        out = ac.place_market_order(
            ticker="AAPL", qty=10.0, side="hodl"
        )
        assert out is None

    def test_zero_qty_returns_none(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        out = ac.place_market_order(
            ticker="AAPL", qty=0, side="buy"
        )
        assert out is None

"""Alpaca paper-trading client (Claude Autonomous experiment).

The TradingClient is ALWAYS constructed with `paper=True`. There is
no live-trading path in this module by design.

When ALPACA_API_KEY/SECRET are missing or `alpaca-py` isn't installed
every helper returns None / empty so the rest of the system keeps
running silently.

Public surface:
    get_trading_client()                              -> TradingClient | None
    get_data_client()                                  -> DataClient | None
    get_account_summary()                              -> dict | None
    get_positions()                                    -> list[dict]
    place_market_order(ticker, qty, side, reasoning)   -> dict | None
    list_recent_orders(days)                           -> list[dict]
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

AUTONOMOUS_TRADES_DIR = ROOT / "data" / "events" / "claude_autonomous_trades"
AUTONOMOUS_TRADES_DIR.mkdir(parents=True, exist_ok=True)

try:  # noqa: SIM105
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False
    TradingClient = None  # type: ignore[assignment]
    StockHistoricalDataClient = None  # type: ignore[assignment]


def alpaca_available() -> bool:
    """True when the SDK is importable AND env keys are configured."""
    if not _ALPACA_AVAILABLE:
        return False
    return bool(
        os.environ.get("ALPACA_API_KEY")
        and os.environ.get("ALPACA_API_SECRET")
    )


def get_trading_client() -> Any | None:
    if not _ALPACA_AVAILABLE:
        return None
    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        return None
    try:
        return TradingClient(api_key, api_secret, paper=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Alpaca trading client init failed: {exc}")
        return None


def get_data_client() -> Any | None:
    if not _ALPACA_AVAILABLE:
        return None
    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        return None
    try:
        return StockHistoricalDataClient(api_key, api_secret)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Alpaca data client init failed: {exc}")
        return None


def get_account_summary() -> dict[str, Any] | None:
    """Returns a JSON-serialisable dict with key account fields, or
    None when the client is unavailable / call fails."""
    client = get_trading_client()
    if client is None:
        return None
    try:
        acc = client.get_account()
        return {
            "account_number": getattr(acc, "account_number", ""),
            "status": str(getattr(acc, "status", "")),
            "currency": getattr(acc, "currency", "USD"),
            "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
            "equity": float(acc.equity),
            "portfolio_value": float(acc.portfolio_value),
            "pattern_day_trader": bool(
                getattr(acc, "pattern_day_trader", False)
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Alpaca get_account failed: {exc}")
        return None


def get_positions() -> list[dict[str, Any]]:
    client = get_trading_client()
    if client is None:
        return []
    try:
        positions = client.get_all_positions()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Alpaca get_all_positions failed: {exc}")
        return []
    out: list[dict[str, Any]] = []
    for p in positions:
        try:
            out.append(
                {
                    "ticker": p.symbol,
                    "shares": float(p.qty),
                    "side": str(p.side.value)
                    if hasattr(p.side, "value") else str(p.side),
                    "market_value": float(p.market_value),
                    "cost_basis": float(p.cost_basis),
                    "current_price": float(p.current_price),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc) * 100.0,
                    "avg_entry_price": float(p.avg_entry_price),
                }
            )
        except (AttributeError, ValueError) as exc:  # noqa: BLE001
            logger.warning(f"Alpaca position parse failed: {exc}")
            continue
    return out


def place_market_order(
    *, ticker: str, qty: float, side: str, reasoning: str = ""
) -> dict[str, Any] | None:
    """Submit a paper market order. Always TIF=DAY. The reasoning
    string is persisted alongside the order for the audit trail."""
    if side.lower() not in {"buy", "sell"}:
        logger.error(f"Invalid order side: {side}")
        return None
    if qty <= 0:
        logger.error(f"Invalid qty: {qty}")
        return None
    client = get_trading_client()
    if client is None:
        return None
    try:
        order_side = (
            OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        )
        request = MarketOrderRequest(
            symbol=ticker.upper().strip(),
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(order_data=request)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Alpaca order submit failed for {ticker}: {exc}")
        return None
    result = {
        "order_id": str(order.id),
        "client_order_id": getattr(order, "client_order_id", None),
        "ticker": ticker.upper().strip(),
        "qty": float(order.qty) if order.qty else qty,
        "side": side.lower(),
        "status": str(order.status.value)
        if hasattr(order.status, "value") else str(order.status),
        "submitted_at": order.submitted_at.isoformat()
        if order.submitted_at else None,
        "reasoning": reasoning,
    }
    _persist_order(result)
    return result


def list_recent_orders(days: int = 14) -> list[dict[str, Any]]:
    client = get_trading_client()
    if client is None:
        return []
    try:
        from alpaca.trading.enums import QueryOrderStatus
        request = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            after=datetime.now(timezone.utc) - timedelta(days=days),
            limit=500,
        )
        orders = client.get_orders(filter=request)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Alpaca list_orders failed: {exc}")
        return []
    out: list[dict[str, Any]] = []
    for o in orders:
        try:
            out.append(
                {
                    "order_id": str(o.id),
                    "ticker": o.symbol,
                    "side": str(o.side.value)
                    if hasattr(o.side, "value") else str(o.side),
                    "qty": float(o.qty) if o.qty else 0.0,
                    "filled_qty": float(o.filled_qty) if o.filled_qty else 0.0,
                    "status": str(o.status.value)
                    if hasattr(o.status, "value") else str(o.status),
                    "submitted_at": o.submitted_at.isoformat()
                    if o.submitted_at else None,
                    "filled_at": o.filled_at.isoformat()
                    if getattr(o, "filled_at", None) else None,
                    "filled_avg_price": float(o.filled_avg_price)
                    if o.filled_avg_price else None,
                }
            )
        except (AttributeError, ValueError):  # noqa: BLE001
            continue
    return out


def _persist_order(order_dict: dict[str, Any]) -> None:
    today = datetime.now(timezone.utc).date()
    f = AUTONOMOUS_TRADES_DIR / f"{today.strftime('%Y-%m')}.jsonl"
    entry = {
        **order_dict,
        "recorded_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    with f.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")

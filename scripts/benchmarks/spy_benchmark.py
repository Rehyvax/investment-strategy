"""SPY benchmark — synthetic snapshot stream.

Holds a fixed nominal of SPY shares so daily returns track the index
1:1. NAV is in *USD* (not EUR) — kept under the `nav_total_eur` key
for shape-compat with the other portfolio readers; the comparator
chart works in % terms anyway.

Public:
    update_spy_snapshot(target_date=today)  -> Path | None
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SPY_DIR = ROOT / "data" / "snapshots" / "spy_benchmark"

NOMINAL_SHARES = 100  # arbitrary scale; only returns matter

logger = logging.getLogger(__name__)


def update_spy_snapshot(
    target_date: date | None = None, *, force: bool = False
) -> Path | None:
    target_date = target_date or date.today()
    SPY_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SPY_DIR / f"{target_date.isoformat()}.json"
    if snap_path.exists() and not force:
        return snap_path
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — SPY snapshot skipped")
        return None
    try:
        hist = yf.Ticker("SPY").history(
            start=(target_date - timedelta(days=5)).isoformat(),
            end=(target_date + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
        if hist is None or hist.empty:
            logger.warning(f"No SPY data for {target_date}")
            return None
        latest_price = float(hist["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"SPY fetch failed for {target_date}: {exc}")
        return None

    nav = round(latest_price * NOMINAL_SHARES, 4)
    snapshot = {
        "as_of_date": target_date.isoformat(),
        "portfolio_id": "spy_benchmark",
        "nav_total_eur": nav,        # USD nominal; field name kept for compat
        "cash_eur": 0.0,
        "currency_base": "USD",
        "positions": [
            {
                "ticker": "SPY",
                "shares": NOMINAL_SHARES,
                "current_price_native": latest_price,
                "current_value_eur": nav,
                "weight_pct": 100.0,
                "sector_at_purchase": "Index",
                "country_at_purchase": "United States",
                "currency": "USD",
            }
        ],
    }
    snap_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snap_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = update_spy_snapshot(force=True)
    print(f"SPY snapshot: {p}")

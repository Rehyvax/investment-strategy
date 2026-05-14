"""Indexa Cartera 10 benchmark — synthetic snapshot stream.

Replicates Indexa's "Cartera 10" (most aggressive equity-heavy) using
US-listed ETF proxies that are easy to fetch via yfinance:
  VTI 45% — US Total Market
  VEA 30% — Developed ex-US
  VWO 10% — Emerging Markets
  VIG  8% — Dividend Growth
  BND  7% — US Total Bond

The real Indexa product uses Vanguard UCITS Ireland equivalents
(IE00B3XXRP09 etc.); the US ADR / NYSE-listed twins track the same
indices closely enough for benchmark comparison.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEXA_DIR = ROOT / "data" / "snapshots" / "indexa_10_benchmark"

INDEXA_10_COMPOSITION = {
    "VTI": 0.45,
    "VEA": 0.30,
    "VWO": 0.10,
    "VIG": 0.08,
    "BND": 0.07,
}
NOMINAL_NAV_USD = 100_000  # arbitrary scale; only returns matter

logger = logging.getLogger(__name__)


def update_indexa_snapshot(
    target_date: date | None = None, *, force: bool = False
) -> Path | None:
    target_date = target_date or date.today()
    INDEXA_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = INDEXA_DIR / f"{target_date.isoformat()}.json"
    if snap_path.exists() and not force:
        return snap_path
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — Indexa snapshot skipped")
        return None

    positions: list[dict] = []
    nav = 0.0
    for ticker, weight in INDEXA_10_COMPOSITION.items():
        try:
            hist = yf.Ticker(ticker).history(
                start=(target_date - timedelta(days=5)).isoformat(),
                end=(target_date + timedelta(days=1)).isoformat(),
                auto_adjust=True,
            )
            if hist is None or hist.empty:
                logger.warning(f"Indexa: no data for {ticker} on {target_date}")
                continue
            price = float(hist["Close"].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Indexa fetch failed for {ticker}: {exc}")
            continue
        target_value = NOMINAL_NAV_USD * weight
        shares = round(target_value / price, 6)
        value = round(shares * price, 4)
        positions.append(
            {
                "ticker": ticker,
                "shares": shares,
                "current_price_native": price,
                "current_value_eur": value,
                "weight_pct": round(weight * 100, 2),
                "sector_at_purchase": "Index ETF",
                "country_at_purchase": "Multi",
                "currency": "USD",
            }
        )
        nav += value
    if not positions:
        return None
    snapshot = {
        "as_of_date": target_date.isoformat(),
        "portfolio_id": "indexa_10_benchmark",
        "nav_total_eur": round(nav, 4),
        "cash_eur": 0.0,
        "currency_base": "USD",
        "composition_source": (
            "Indexa Cartera 10 — replica via US-listed Vanguard ETFs."
        ),
        "positions": positions,
    }
    snap_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snap_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = update_indexa_snapshot(force=True)
    print(f"Indexa snapshot: {p}")

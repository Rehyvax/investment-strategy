"""Fundamentals analyst — yfinance .info ratios + interpretive flags.

Pulls a handful of stable ratios from yfinance per ticker and tags
qualitative red-flags (high P/E, high leverage, liquidity concern,
operating loss, strong revenue growth, revenue decline). The flags
list is consumed by the LLM-driven position opinion to keep the
narrative grounded in data rather than vibes.

Public surface:
  compute_fundamentals(ticker)               -> dict
  compute_all_fundamentals_for_portfolio()   -> {ticker: dict}
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("fundamentals_analyst")

SNAPSHOTS_DIR = ROOT / "data" / "snapshots"


# ---------------------------------------------------------------------------
# Flag thresholds — kept as module constants so tests can pin them
# ---------------------------------------------------------------------------
FLAG_HIGH_PE = 40.0
FLAG_LOW_PE = 10.0
FLAG_HIGH_LEVERAGE_DE = 150.0          # debt/equity ratio (yfinance pct-style)
FLAG_LIQUIDITY_CR = 1.0                # current ratio
FLAG_STRONG_REV_GROWTH = 0.20          # revenue_growth y/y
FLAG_REV_DECLINE = -0.05


# ---------------------------------------------------------------------------
# Single-ticker fundamentals
# ---------------------------------------------------------------------------
def compute_fundamentals(ticker: str) -> dict[str, Any]:
    """Returns a dict of ratios + `flags` (list[str]). Returns
    `{"ticker": ..., "error": "..."}` on hard failure."""
    try:
        import yfinance as yf
    except ImportError:
        return {"ticker": ticker, "error": "yfinance_missing"}

    try:
        t = yf.Ticker(ticker)
        # `Ticker.info` raises or returns {} on bad ticker; both are
        # handled.
        try:
            info = t.info or {}
        except Exception as exc:  # noqa: BLE001
            return {"ticker": ticker, "error": f"info_fetch_failed: {exc}"}
        if not info or not info.get("symbol"):
            return {"ticker": ticker, "error": "no_info"}

        result: dict[str, Any] = {
            "ticker": ticker,
            "as_of_date": date.today().isoformat(),
            # Valuation
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "peg_ratio": info.get("pegRatio"),
            # Profitability
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
            "profit_margin": info.get("profitMargins"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            # Health
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),
            # Growth
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            # Cash flow
            "fcf": info.get("freeCashflow"),
            "operating_cashflow": info.get("operatingCashflow"),
            # Meta
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "country": info.get("country"),
            # Analyst targets
            "target_mean_price": info.get("targetMeanPrice"),
            "recommendation_key": info.get("recommendationKey"),
            "number_of_analyst_opinions": info.get("numberOfAnalystOpinions"),
        }
        result["flags"] = compute_flags(result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Fundamentals fetch failed for {ticker}: {exc}")
        return {"ticker": ticker, "error": str(exc)}


def compute_flags(metrics: dict[str, Any]) -> list[str]:
    """Pure function — given a metrics dict, returns the list of
    qualitative flags. Centralized so tests can target it without
    yfinance roundtrip."""
    flags: list[str] = []
    pe = metrics.get("pe_ratio")
    if isinstance(pe, (int, float)) and pe > FLAG_HIGH_PE:
        flags.append("high_pe")
    if isinstance(pe, (int, float)) and 0 < pe < FLAG_LOW_PE:
        flags.append("low_pe")
    de = metrics.get("debt_to_equity")
    if isinstance(de, (int, float)) and de > FLAG_HIGH_LEVERAGE_DE:
        flags.append("high_leverage")
    cr = metrics.get("current_ratio")
    if isinstance(cr, (int, float)) and cr < FLAG_LIQUIDITY_CR:
        flags.append("liquidity_concern")
    om = metrics.get("operating_margin")
    if isinstance(om, (int, float)) and om < 0:
        flags.append("operating_loss")
    rg = metrics.get("revenue_growth")
    if isinstance(rg, (int, float)) and rg > FLAG_STRONG_REV_GROWTH:
        flags.append("strong_revenue_growth")
    if isinstance(rg, (int, float)) and rg < FLAG_REV_DECLINE:
        flags.append("revenue_decline")
    return flags


# ---------------------------------------------------------------------------
# Portfolio walker
# ---------------------------------------------------------------------------
def _load_latest_snapshot(portfolio_id: str = "real") -> dict[str, Any] | None:
    pdir = SNAPSHOTS_DIR / portfolio_id
    if not pdir.exists():
        return None
    candidates: list[Path] = []
    for f in pdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            candidates.append(f)
    if not candidates:
        return None
    candidates.sort()
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def compute_all_fundamentals_for_portfolio(
    portfolio_id: str = "real",
) -> dict[str, dict[str, Any]]:
    """Returns a `{ticker: metrics_dict}` mapping for every position in
    the latest snapshot of `portfolio_id`. Tickers whose .info call
    fails are silently dropped from the output."""
    snap = _load_latest_snapshot(portfolio_id)
    if snap is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for pos in snap.get("positions", []) or []:
        ticker = pos.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            continue
        result = compute_fundamentals(ticker)
        if "error" in result:
            logger.info(f"  skip {ticker}: {result['error']}")
            continue
        out[ticker] = result
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = compute_all_fundamentals_for_portfolio()
    print(json.dumps(out, indent=2, ensure_ascii=False))

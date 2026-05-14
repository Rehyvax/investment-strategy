"""HRP paper portfolio (López de Prado Hierarchical Risk Parity).

Runs daily over the same universe as the real portfolio (snapshot
positions). When `riskfolio-lib` is installed it uses the standard
HRP optimization; otherwise it falls back to inverse-volatility
weighting — both produce risk-aware allocations and can be compared
against the real-portfolio decisions.

Public:
    compute_hrp_weights(tickers, lookback_days=90) -> dict[str, float]
    update_hrp_snapshot(target_date=today)         -> Path | None
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
HRP_DIR = ROOT / "data" / "snapshots" / "hrp_paper"
REAL_DIR = ROOT / "data" / "snapshots" / "real"

NOMINAL_NAV_EUR = 50_000

logger = logging.getLogger(__name__)


def _equal_weight(tickers: Iterable[str]) -> dict[str, float]:
    tickers = list(tickers)
    if not tickers:
        return {}
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def _inverse_volatility(
    tickers: list[str], lookback_days: int = 90
) -> dict[str, float]:
    try:
        import yfinance as yf
    except ImportError:
        return _equal_weight(tickers)
    end = date.today()
    start = end - timedelta(days=lookback_days + 10)
    inv_vols: dict[str, float] = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(
                start=start.isoformat(), end=end.isoformat(),
                auto_adjust=True,
            )
            if hist is None or hist.empty or len(hist) < 20:
                continue
            vol = float(hist["Close"].pct_change().std())
            if vol > 0:
                inv_vols[t] = 1.0 / vol
        except Exception:  # noqa: BLE001
            continue
    total = sum(inv_vols.values())
    if total == 0:
        return _equal_weight(tickers)
    return {t: v / total for t, v in inv_vols.items()}


def compute_hrp_weights(
    tickers: list[str], lookback_days: int = 90
) -> dict[str, float]:
    """Try riskfolio-lib HRP first; fall back to inverse-vol or equal
    weight on any failure. Always returns a dict with weights summing
    to ~1.0."""
    if not tickers:
        return {}
    try:
        import pandas as pd
        import riskfolio as rp  # type: ignore
        import yfinance as yf
    except ImportError:
        logger.info("riskfolio-lib not installed — using inverse-vol fallback")
        return _inverse_volatility(tickers, lookback_days)
    try:
        end = date.today()
        start = end - timedelta(days=lookback_days + 30)
        prices: dict[str, "pd.Series"] = {}
        for t in tickers:
            try:
                hist = yf.Ticker(t).history(
                    start=start.isoformat(), end=end.isoformat(),
                    auto_adjust=True,
                )
                if hist is not None and not hist.empty and len(hist) >= 30:
                    prices[t] = hist["Close"]
            except Exception:  # noqa: BLE001
                continue
        if len(prices) < 5:
            return _inverse_volatility(tickers, lookback_days)
        prices_df = pd.DataFrame(prices).dropna()
        returns = prices_df.pct_change().dropna()
        if len(returns) < 30:
            return _inverse_volatility(list(prices.keys()), lookback_days)
        port = rp.HCPortfolio(returns=returns)
        w = port.optimization(
            model="HRP",
            codependence="pearson",
            rm="MV",
            rf=0,
            linkage="single",
            max_k=10,
            leaf_order=True,
        )
        return {t: float(w.loc[t].iloc[0]) for t in w.index}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"HRP failed ({exc}) — using inverse-vol fallback")
        return _inverse_volatility(tickers, lookback_days)


def _load_real_universe() -> list[str]:
    if not REAL_DIR.exists():
        return []
    cands = sorted(
        f for f in REAL_DIR.glob("*.json")
        if not f.name.startswith("_")
        and len(f.stem) == 10 and f.stem[4] == "-"
    )
    if not cands:
        return []
    try:
        snap = json.loads(cands[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [
        p.get("ticker") for p in snap.get("positions", []) or []
        if isinstance(p.get("ticker"), str)
    ]


def update_hrp_snapshot(
    target_date: date | None = None, *, force: bool = False
) -> Path | None:
    target_date = target_date or date.today()
    HRP_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = HRP_DIR / f"{target_date.isoformat()}.json"
    if snap_path.exists() and not force:
        return snap_path
    tickers = _load_real_universe()
    if len(tickers) < 5:
        logger.warning("HRP: real universe < 5 tickers, skipping")
        return None
    weights = compute_hrp_weights(tickers, lookback_days=90)
    if not weights:
        return None

    try:
        import yfinance as yf
    except ImportError:
        return None

    positions: list[dict] = []
    nav = 0.0
    for ticker, weight in weights.items():
        try:
            hist = yf.Ticker(ticker).history(
                start=(target_date - timedelta(days=5)).isoformat(),
                end=(target_date + timedelta(days=1)).isoformat(),
                auto_adjust=True,
            )
            if hist is None or hist.empty:
                continue
            price = float(hist["Close"].iloc[-1])
        except Exception:  # noqa: BLE001
            continue
        value = NOMINAL_NAV_EUR * weight
        shares = round(value / price, 6) if price > 0 else 0.0
        actual_value = round(shares * price, 4)
        positions.append(
            {
                "ticker": ticker,
                "shares": shares,
                "current_price_native": price,
                "current_value_eur": actual_value,
                "weight_pct": round(weight * 100, 4),
                "currency": "USD",
            }
        )
        nav += actual_value
    if not positions:
        return None
    snapshot = {
        "as_of_date": target_date.isoformat(),
        "portfolio_id": "hrp_paper",
        "nav_total_eur": round(nav, 4),
        "cash_eur": 0.0,
        "optimization_method": "HRP_or_inverse_vol_fallback",
        "lookback_days": 90,
        "positions": positions,
    }
    snap_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snap_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = update_hrp_snapshot(force=True)
    print(f"HRP snapshot: {p}")

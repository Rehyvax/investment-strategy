"""Technical analyst — yfinance OHLCV + manual indicator computation.

Indicators computed (numpy/pandas only, no pandas-ta dependency):
  MA50, MA200, RSI(14), MACD(12,26,9), Bollinger Bands(20,2)

Each ticker yields an interpretation block (`trend`, `rsi_signal`,
`macd_signal`, `bb_position`) so the LLM-driven position opinion can
read a single struct per ticker without re-deriving labels.

Public surface:
  compute_indicators(ticker)              -> dict
  compute_all_technicals_for_portfolio()  -> {ticker: dict}
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("technical_analyst")

SNAPSHOTS_DIR = ROOT / "data" / "snapshots"


# ---------------------------------------------------------------------------
# Core: indicator computation
# ---------------------------------------------------------------------------
def compute_indicators(ticker: str, period_days: int = 280) -> dict[str, Any]:
    """Fetch ~280 calendar days of OHLCV (≈195 trading days) and compute
    indicators. Returns `{"ticker": ticker, "error": "..."}` on failure
    so the caller can filter cleanly without raising."""
    try:
        import yfinance as yf
    except ImportError:
        return {"ticker": ticker, "error": "yfinance_missing"}

    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)
        t = yf.Ticker(ticker)
        df = t.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=True,
        )
        if df is None or df.empty or len(df) < 30:
            return {"ticker": ticker, "error": "insufficient_data"}

        close = df["Close"]

        # Moving averages
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean() if len(df) >= 200 else None

        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi14 = 100 - (100 / (1 + rs))

        # MACD(12,26,9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal

        # Bollinger Bands(20, 2)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std

        # Latest snapshot
        price = float(close.iloc[-1])
        ma50_v = (
            float(ma50.iloc[-1])
            if ma50 is not None and not _is_nan(ma50.iloc[-1])
            else None
        )
        ma200_v = (
            float(ma200.iloc[-1])
            if ma200 is not None and not _is_nan(ma200.iloc[-1])
            else None
        )
        rsi_v = float(rsi14.iloc[-1]) if not _is_nan(rsi14.iloc[-1]) else 50.0
        macd_v = float(macd.iloc[-1]) if not _is_nan(macd.iloc[-1]) else 0.0
        macd_sig_v = (
            float(macd_signal.iloc[-1])
            if not _is_nan(macd_signal.iloc[-1])
            else 0.0
        )
        macd_hist_v = (
            float(macd_hist.iloc[-1])
            if not _is_nan(macd_hist.iloc[-1])
            else 0.0
        )
        bb_upper_v = (
            float(bb_upper.iloc[-1])
            if not _is_nan(bb_upper.iloc[-1])
            else None
        )
        bb_lower_v = (
            float(bb_lower.iloc[-1])
            if not _is_nan(bb_lower.iloc[-1])
            else None
        )
        prev_hist = (
            float(macd_hist.iloc[-2])
            if len(macd_hist) >= 2 and not _is_nan(macd_hist.iloc[-2])
            else 0.0
        )

        trend = classify_trend(price, ma50_v, ma200_v)
        rsi_signal_label = classify_rsi(rsi_v)
        macd_signal_label = classify_macd(macd_hist_v, prev_hist)
        bb_position = classify_bbands(price, bb_upper_v, bb_lower_v)

        return {
            "ticker": ticker,
            "as_of_date": end_date.isoformat(),
            "price": round(price, 4),
            "ma50": round(ma50_v, 4) if ma50_v is not None else None,
            "ma200": round(ma200_v, 4) if ma200_v is not None else None,
            "rsi14": round(rsi_v, 2),
            "macd": round(macd_v, 6),
            "macd_signal_value": round(macd_sig_v, 6),
            "macd_histogram": round(macd_hist_v, 6),
            "bb_upper": round(bb_upper_v, 4) if bb_upper_v is not None else None,
            "bb_lower": round(bb_lower_v, 4) if bb_lower_v is not None else None,
            "trend": trend,
            "rsi_signal": rsi_signal_label,
            "macd_signal": macd_signal_label,
            "bb_position": bb_position,
            "bars_used": int(len(df)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Indicator computation failed for {ticker}: {exc}")
        return {"ticker": ticker, "error": str(exc)}


# ---------------------------------------------------------------------------
# Pure classifiers (unit-testable, no I/O)
# ---------------------------------------------------------------------------
def classify_trend(
    price: float, ma50: float | None, ma200: float | None
) -> str:
    if ma200 is not None and ma50 is not None:
        if price > ma50 > ma200:
            return "bullish_strong"
        if price < ma50 < ma200:
            return "bearish_strong"
    if ma50 is not None and price > ma50:
        return "bullish_mild"
    if ma50 is not None and price < ma50:
        return "bearish_mild"
    return "neutral"


def classify_rsi(rsi: float) -> str:
    if rsi > 70:
        return "overbought"
    if rsi < 30:
        return "oversold"
    if rsi > 60:
        return "strong_momentum"
    if rsi < 40:
        return "weak_momentum"
    return "neutral"


def classify_macd(hist_now: float, hist_prev: float) -> str:
    if hist_now > 0 and hist_prev <= 0:
        return "bullish_cross"
    if hist_now < 0 and hist_prev >= 0:
        return "bearish_cross"
    if hist_now > 0:
        return "bullish_momentum"
    if hist_now < 0:
        return "bearish_momentum"
    return "neutral"


def classify_bbands(
    price: float, upper: float | None, lower: float | None
) -> str:
    if upper is None or lower is None:
        return "unknown"
    midpoint = (upper + lower) / 2
    if price > upper:
        return "above_upper"
    if price < lower:
        return "below_lower"
    if price > midpoint:
        return "upper_half"
    return "lower_half"


def _is_nan(x: Any) -> bool:
    try:
        return x != x  # NaN != NaN
    except Exception:  # noqa: BLE001
        return False


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


def compute_all_technicals_for_portfolio(
    as_of_date: date | None = None, portfolio_id: str = "real"
) -> dict[str, dict[str, Any]]:
    """Compute technicals for every ticker in the latest portfolio snapshot.
    Tickers whose computation fails are silently dropped from the output —
    the caller keeps a complete dict with no error rows."""
    _ = as_of_date  # reserved for future point-in-time support
    snap = _load_latest_snapshot(portfolio_id)
    if snap is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for pos in snap.get("positions", []) or []:
        ticker = pos.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            continue
        result = compute_indicators(ticker)
        if "error" in result:
            logger.info(f"  skip {ticker}: {result['error']}")
            continue
        out[ticker] = result
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = compute_all_technicals_for_portfolio()
    print(json.dumps(out, indent=2, ensure_ascii=False))

"""Risk-adjusted return metrics computed from snapshot NAV history.

Pure functions over numpy arrays; the I/O layer (`compute_daily_returns`)
walks `data/snapshots/{portfolio_id}/*.json` for the trailing window.

Public surface:
    compute_daily_returns(portfolio_id, lookback_days)  -> list[float]
    sharpe_ratio(returns, rf_annual=0.04)               -> float | None
    sortino_ratio(returns, rf_annual=0.04)              -> float | None
    max_drawdown(returns)                                -> float | None  (% pct)
    calmar_ratio(returns)                                -> float | None
    information_ratio(returns, benchmark_returns)        -> float | None
    compute_all_metrics(portfolio_id, lookback_days)     -> dict
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"

MIN_OBSERVATIONS = 10
TRADING_DAYS_PER_YEAR = 252
DEFAULT_RF_ANNUAL = 0.04


# ---------------------------------------------------------------------------
# I/O — daily returns from snapshot NAVs
# ---------------------------------------------------------------------------
def compute_daily_returns(
    portfolio_id: str = "real",
    lookback_days: int = 90,
    *,
    snapshots_dir: Path | None = None,
) -> list[float]:
    """Walk snapshot files for `portfolio_id`, sort by date, return
    daily NAV-to-NAV returns over the trailing window."""
    sdir = (snapshots_dir or SNAPSHOTS_DIR) / portfolio_id
    if not sdir.exists():
        return []
    snaps: list[tuple[date, float]] = []
    cutoff = date.today() - timedelta(days=lookback_days)
    for f in sdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if not (len(stem) == 10 and stem[4] == "-" and stem[7] == "-"):
            continue
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue
        if d < cutoff:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        nav = data.get("nav_total_eur") or data.get("equity") or 0.0
        try:
            nav = float(nav)
        except (TypeError, ValueError):
            continue
        if nav > 0:
            snaps.append((d, nav))
    snaps.sort(key=lambda x: x[0])
    if len(snaps) < 2:
        return []
    navs = [n for _, n in snaps]
    return [
        (navs[i] - navs[i - 1]) / navs[i - 1]
        for i in range(1, len(navs))
    ]


# ---------------------------------------------------------------------------
# Pure metric functions
# ---------------------------------------------------------------------------
def _arr(returns: Iterable[float]) -> np.ndarray:
    return np.asarray(list(returns), dtype=float)


def sharpe_ratio(
    returns: Iterable[float], rf_annual: float = DEFAULT_RF_ANNUAL
) -> float | None:
    arr = _arr(returns)
    if len(arr) < MIN_OBSERVATIONS:
        return None
    std = float(arr.std(ddof=1))
    if std == 0:
        return None
    excess_daily = float(arr.mean()) - (rf_annual / TRADING_DAYS_PER_YEAR)
    return round((excess_daily / std) * np.sqrt(TRADING_DAYS_PER_YEAR), 3)


def sortino_ratio(
    returns: Iterable[float], rf_annual: float = DEFAULT_RF_ANNUAL
) -> float | None:
    arr = _arr(returns)
    if len(arr) < MIN_OBSERVATIONS:
        return None
    downside = arr[arr < 0]
    if len(downside) == 0:
        return None  # No losses → Sortino undefined
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
    if downside_std == 0:
        return None
    excess_daily = float(arr.mean()) - (rf_annual / TRADING_DAYS_PER_YEAR)
    return round(
        (excess_daily / downside_std) * np.sqrt(TRADING_DAYS_PER_YEAR), 3
    )


def max_drawdown(returns: Iterable[float]) -> float | None:
    """Returns max DD as a NEGATIVE percent (e.g. -8.42)."""
    arr = _arr(returns)
    if len(arr) < 2:
        return None
    cum = np.cumprod(1 + arr)
    running_max = np.maximum.accumulate(cum)
    dd = (cum - running_max) / running_max
    return round(float(dd.min()) * 100.0, 2)


def calmar_ratio(returns: Iterable[float]) -> float | None:
    arr = _arr(returns)
    if len(arr) < 30:
        return None
    cum_return = float(np.prod(1 + arr) - 1.0)
    years = len(arr) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return None
    cagr = (1 + cum_return) ** (1 / years) - 1
    mdd = max_drawdown(arr)
    if mdd is None or mdd == 0:
        return None
    return round(cagr / abs(mdd / 100.0), 3)


def information_ratio(
    returns: Iterable[float], benchmark_returns: Iterable[float]
) -> float | None:
    a = _arr(returns)
    b = _arr(benchmark_returns)
    if len(a) < 20 or len(a) != len(b):
        return None
    active = a - b
    std = float(active.std(ddof=1))
    if std == 0:
        return None
    return round(
        (float(active.mean()) / std) * np.sqrt(TRADING_DAYS_PER_YEAR), 3
    )


def cagr_estimated_pct(returns: Iterable[float]) -> float | None:
    arr = _arr(returns)
    if len(arr) < 2:
        return None
    cum = float(np.prod(1 + arr))
    if cum <= 0:
        return None
    return round((cum ** (TRADING_DAYS_PER_YEAR / len(arr)) - 1) * 100.0, 2)


# ---------------------------------------------------------------------------
# One-shot rollup
# ---------------------------------------------------------------------------
def compute_all_metrics(
    portfolio_id: str = "real",
    lookback_days: int = 90,
    *,
    snapshots_dir: Path | None = None,
    benchmark_id: str = "spy_benchmark",
) -> dict[str, Any]:
    returns = compute_daily_returns(
        portfolio_id, lookback_days, snapshots_dir=snapshots_dir
    )
    if len(returns) < MIN_OBSERVATIONS:
        return {
            "status": "insufficient_data",
            "n_observations": len(returns),
            "lookback_days": lookback_days,
            "message": (
                f"Necesita al menos {MIN_OBSERVATIONS} días de retornos, "
                f"hay {len(returns)}."
            ),
        }
    benchmark_returns = compute_daily_returns(
        benchmark_id, lookback_days, snapshots_dir=snapshots_dir
    )
    ir: float | None = None
    if benchmark_returns and len(benchmark_returns) == len(returns):
        ir = information_ratio(returns, benchmark_returns)
    return {
        "status": "ok",
        "portfolio_id": portfolio_id,
        "n_observations": len(returns),
        "lookback_days": lookback_days,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "calmar": calmar_ratio(returns),
        "max_drawdown_pct": max_drawdown(returns),
        f"information_ratio_vs_{benchmark_id}": ir,
        "cagr_estimated_pct": cagr_estimated_pct(returns),
    }

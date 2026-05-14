"""T+7 reflection loop specific to Claude Autonomous decisions.

For each autonomous decision recorded N days ago, compares the
realized claude_autonomous portfolio return vs SPY over the same
window. Persists to data/events/claude_autonomous_reflections/ and
rolls up a 30-day Brier score (`claude_autonomous_brier_30d`).

Public:
    run_autonomous_reflections(lookforward=7) -> dict
    aggregate_autonomous_brier(days=30)        -> dict
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.metrics.risk_adjusted import compute_daily_returns  # noqa: E402

DECISIONS_DIR = ROOT / "data" / "events" / "claude_autonomous_decisions"
REFLECTIONS_DIR = ROOT / "data" / "events" / "claude_autonomous_reflections"
REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def find_decisions_on(target_date: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not DECISIONS_DIR.exists():
        return out
    for f in DECISIONS_DIR.glob("*.jsonl"):
        for ev in _iter_jsonl(f):
            ts = ev.get("timestamp", "")
            try:
                d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                continue
            if d == target_date:
                out.append(ev)
    return out


def existing_reflection_keys() -> set[str]:
    keys: set[str] = set()
    if not REFLECTIONS_DIR.exists():
        return keys
    for f in REFLECTIONS_DIR.glob("*.jsonl"):
        for r in _iter_jsonl(f):
            ts = r.get("decision_timestamp")
            if isinstance(ts, str):
                keys.add(ts)
    return keys


def _portfolio_return_pct(
    portfolio_id: str, lookforward: int
) -> float | None:
    returns = compute_daily_returns(
        portfolio_id, lookback_days=lookforward
    )
    if not returns:
        return None
    cum = 1.0
    for r in returns:
        cum *= 1.0 + r
    return (cum - 1.0) * 100.0


def reflect_on_decision(
    decision: dict[str, Any], *, lookforward_days: int = 7
) -> dict[str, Any] | None:
    ts = decision.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        d_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except ValueError:
        return None
    decision_type = decision.get("decision_type", "hold")
    # Realized claude vs SPY over the lookforward window.
    claude_ret = _portfolio_return_pct("claude_autonomous", lookforward_days)
    spy_ret = _portfolio_return_pct("spy_benchmark", lookforward_days)
    if claude_ret is None or spy_ret is None:
        return None
    alpha = claude_ret - spy_ret
    # Brier expectation: a "trade" implies expecting to beat SPY; a
    # "hold" implies the current allocation already does. Either way,
    # correctness = realized alpha > 0.
    expected_alpha_positive = decision_type in {"trade", "rebalance", "hold"}
    actual_alpha_positive = alpha > 0
    brier_correct = (
        1 if expected_alpha_positive == actual_alpha_positive else 0
    )
    return {
        "decision_timestamp": ts,
        "decision_type": decision_type,
        "decision_date": d_date.isoformat(),
        "lookforward_days": lookforward_days,
        "claude_return_pct": round(claude_ret, 4),
        "spy_return_pct": round(spy_ret, 4),
        "alpha_pct": round(alpha, 4),
        "expected_alpha_positive": expected_alpha_positive,
        "actual_alpha_positive": actual_alpha_positive,
        "brier_correct": brier_correct,
        "reflection_timestamp": (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "lesson": (
            f"Autonomous {decision_type} produced {alpha:+.2f}% alpha vs SPY "
            f"over {lookforward_days}d."
        ),
    }


def run_autonomous_reflections(
    *, lookforward_days: int = 7, target_date: date | None = None
) -> dict[str, Any]:
    target = target_date or (date.today() - timedelta(days=lookforward_days))
    decisions = find_decisions_on(target)
    seen = existing_reflection_keys()
    new_lines: list[str] = []
    new_count = 0
    for d in decisions:
        ts = d.get("timestamp")
        if not ts or ts in seen:
            continue
        result = reflect_on_decision(d, lookforward_days=lookforward_days)
        if result is None:
            continue
        new_lines.append(json.dumps(result, ensure_ascii=False))
        new_count += 1
    if new_lines:
        f = REFLECTIONS_DIR / f"{date.today().strftime('%Y-%m')}.jsonl"
        existing = (
            f.read_text(encoding="utf-8") if f.exists() else ""
        )
        if existing and not existing.endswith("\n"):
            existing += "\n"
        body = existing + "\n".join(new_lines) + "\n"
        tmp = f.with_suffix(".jsonl.tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(f)
    rollup = aggregate_autonomous_brier(30)
    return {
        "new_reflections_count": new_count,
        "target_date": target.isoformat(),
        "claude_autonomous_brier_30d": rollup["score"],
        "n_evaluations_30d": rollup["n"],
    }


def aggregate_autonomous_brier(days: int = 30) -> dict[str, Any]:
    if not REFLECTIONS_DIR.exists():
        return {"score": None, "n": 0}
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")
    recent: list[dict[str, Any]] = []
    for f in REFLECTIONS_DIR.glob("*.jsonl"):
        for r in _iter_jsonl(f):
            if (r.get("reflection_timestamp") or "") >= cutoff:
                recent.append(r)
    if not recent:
        return {"score": None, "n": 0}
    score = sum(int(r.get("brier_correct") or 0) for r in recent) / len(recent)
    return {"score": round(score, 3), "n": len(recent)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = run_autonomous_reflections()
    print(json.dumps(out, indent=2))

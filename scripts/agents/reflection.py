"""Reflection loop — measure realized returns vs predicted direction
of past debates, compute Brier scoring, write transferable lessons.

Workflow:
    1. Walk all debate verdicts from N days ago (default 7).
    2. For each, fetch the realized price return over the same window
       via yfinance, plus SPY return for alpha.
    3. Map the verdict's `suggested_action` (or `verdict`) to an
       expected direction (`up` / `down`).
    4. Brier-correct = 1 if predicted direction matches realized
       direction, 0 otherwise (binary, not probabilistic — we don't
       have explicit probability output yet).
    5. Optionally, ask the LLM to extract 1-2 transferable lessons.
    6. Persist to data/events/reflections/{YYYY-MM}.jsonl, dedup on
       (ticker, debate_timestamp).
    7. Roll up a 30-day Brier average for the cerebro sidebar widget.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from llm_narratives import MODEL, get_client  # noqa: E402

DEBATES_DIR = ROOT / "data" / "events" / "debates"
REFLECTIONS_DIR = ROOT / "data" / "events" / "reflections"
REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)


REFLECTION_SYSTEM_PROMPT = """You are a Reflection Agent. Your role is to
evaluate past recommendations against realized returns and extract
lessons.

Rules:
- Compare predicted action vs realized outcome.
- Identify WHY the recommendation worked or failed.
- Extract 1-2 TRANSFERABLE lessons (general patterns, not specific to
  the ticker).
- Be specific, not generic ("trust the data" is useless).
- Avoid hindsight bias — judge based on info available at decision time.
- Tone: analytical, honest, no defensiveness."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def expected_direction_from_verdict(verdict_entry: dict[str, Any]) -> str:
    """Map a debate verdict's `suggested_action` + `verdict` to an
    expected price direction (`up` or `down`).

    Pure function — covered by unit tests."""
    suggested = (verdict_entry.get("suggested_action") or "").lower()
    verdict = (verdict_entry.get("verdict") or "").lower()
    if (
        "exit" in suggested
        or "reduce" in suggested
        or "weakened" in verdict
        or "invalidated" in verdict
    ):
        return "down"
    return "up"


def brier_correct(expected: str, actual: str) -> int:
    """Binary correctness — 1 when directions match, 0 otherwise."""
    return 1 if expected == actual else 0


def fetch_realized_return(
    ticker: str, from_date: str, to_date: str
) -> dict[str, Any] | None:
    """Returns `{"from_price", "to_price", "raw_return_pct"}` or None
    on failure (no rows / network error / yfinance missing)."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.Ticker(ticker).history(
            start=from_date, end=to_date, auto_adjust=True
        )
        if df is None or df.empty or len(df) < 2:
            return None
        from_price = float(df["Close"].iloc[0])
        to_price = float(df["Close"].iloc[-1])
        if from_price <= 0:
            return None
        return {
            "from_price": from_price,
            "to_price": to_price,
            "raw_return_pct": (to_price - from_price) / from_price * 100.0,
        }
    except Exception:  # noqa: BLE001
        return None


def fetch_spy_return(from_date: str, to_date: str) -> float | None:
    spy = fetch_realized_return("SPY", from_date, to_date)
    return spy["raw_return_pct"] if spy else None


# ---------------------------------------------------------------------------
# Reflection per debate
# ---------------------------------------------------------------------------
def reflect_on_debate(
    debate_entry: dict[str, Any],
    *,
    lookforward_days: int = 7,
    fetch_returns_fn=fetch_realized_return,
    fetch_spy_fn=fetch_spy_return,
) -> dict[str, Any] | None:
    """Compute the reflection record for a single past debate.
    `fetch_returns_fn` and `fetch_spy_fn` are injected for tests."""
    ticker = debate_entry.get("ticker")
    timestamp = debate_entry.get("timestamp", "")
    if not ticker or not timestamp:
        return None
    try:
        debate_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    debate_d = debate_dt.date()
    from_date = debate_d.isoformat()
    to_date = (debate_d + timedelta(days=lookforward_days)).isoformat()

    realized = fetch_returns_fn(ticker, from_date, to_date)
    if realized is None:
        return None
    spy_return = fetch_spy_fn(from_date, to_date)
    alpha = realized["raw_return_pct"] - (spy_return or 0.0)

    expected = expected_direction_from_verdict(debate_entry)
    actual = "up" if realized["raw_return_pct"] > 0 else "down"
    correct = brier_correct(expected, actual)

    reflection_text: str | None = None
    client = get_client()
    if client is not None:
        try:
            prompt = (
                f"Debate from {timestamp[:10]} on {ticker}:\n"
                f"Verdict: {debate_entry.get('verdict')}\n"
                f"Suggested action: {debate_entry.get('suggested_action')}\n"
                f"Confidence: {debate_entry.get('confidence', 'unknown')}\n"
                f"Bull key argument: "
                f"{(debate_entry.get('bull_rounds') or [''])[0][:300]}\n"
                f"Bear key argument: "
                f"{(debate_entry.get('bear_rounds') or [''])[0][:300]}\n\n"
                f"Realized return ({lookforward_days}d): "
                f"{realized['raw_return_pct']:+.2f}% "
                f"(alpha vs SPY: {alpha:+.2f}%)\n\n"
                "Was this recommendation correct? Why or why not?\n"
                "Extract 1-2 transferable lessons (general patterns, "
                f"not specific to {ticker}). 4-6 sentences total."
            )
            response = client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=REFLECTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            block = response.content[0]
            reflection_text = (getattr(block, "text", None) or "").strip()
        except Exception as exc:  # noqa: BLE001
            print(f"Reflection LLM error for {ticker}: {exc}")
            reflection_text = None

    return {
        "ticker": ticker,
        "debate_timestamp": timestamp,
        "reflection_timestamp": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "lookforward_days": lookforward_days,
        "from_date": from_date,
        "to_date": to_date,
        "realized_return_pct": round(realized["raw_return_pct"], 2),
        "alpha_vs_spy_pct": round(alpha, 2),
        "expected_direction": expected,
        "actual_direction": actual,
        "brier_correct": correct,
        "reflection_text": reflection_text or "(LLM unavailable)",
    }


# ---------------------------------------------------------------------------
# Disk walkers
# ---------------------------------------------------------------------------
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


def find_debates_on(target_date: date, *, debates_dir: Path | None = None) -> list[dict[str, Any]]:
    debates_dir = debates_dir or DEBATES_DIR
    out: list[dict[str, Any]] = []
    if not debates_dir.exists():
        return out
    for f in debates_dir.glob("*.jsonl"):
        for entry in _iter_jsonl(f):
            ts = entry.get("timestamp", "")
            try:
                d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                continue
            if d == target_date:
                out.append(entry)
    return out


def existing_reflection_keys(
    *, reflections_dir: Path | None = None
) -> set[tuple[str, str]]:
    reflections_dir = reflections_dir or REFLECTIONS_DIR
    keys: set[tuple[str, str]] = set()
    if not reflections_dir.exists():
        return keys
    for f in reflections_dir.glob("*.jsonl"):
        for r in _iter_jsonl(f):
            t = r.get("ticker")
            ts = r.get("debate_timestamp")
            if t and ts:
                keys.add((t, ts))
    return keys


def _atomic_append(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    body = existing + "\n".join(lines) + "\n"
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def aggregate_brier(
    days: int = 30, *, reflections_dir: Path | None = None
) -> dict[str, Any]:
    """Roll up reflections in the trailing window. Returns
    `{"score": float|None, "n": int}`."""
    reflections_dir = reflections_dir or REFLECTIONS_DIR
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")
    recent: list[dict[str, Any]] = []
    if not reflections_dir.exists():
        return {"score": None, "n": 0}
    for f in reflections_dir.glob("*.jsonl"):
        for r in _iter_jsonl(f):
            if (r.get("reflection_timestamp") or "") >= cutoff:
                recent.append(r)
    if not recent:
        return {"score": None, "n": 0}
    score = sum(int(r.get("brier_correct") or 0) for r in recent) / len(recent)
    return {"score": round(score, 3), "n": len(recent)}


def run_reflections(
    *,
    target_date: date | None = None,
    lookforward_days: int = 7,
    debates_dir: Path | None = None,
    reflections_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate reflections for debates that happened `lookforward_days`
    ago. Skips debates already reflected. Returns a summary dict."""
    target = target_date or (date.today() - timedelta(days=lookforward_days))
    debates_dir = debates_dir or DEBATES_DIR
    reflections_dir = reflections_dir or REFLECTIONS_DIR

    debates = find_debates_on(target, debates_dir=debates_dir)
    seen = existing_reflection_keys(reflections_dir=reflections_dir)
    new_lines: list[str] = []
    new_count = 0
    for d in debates:
        key = (d.get("ticker"), d.get("timestamp"))
        if key in seen:
            continue
        result = reflect_on_debate(d, lookforward_days=lookforward_days)
        if result is None:
            continue
        new_lines.append(json.dumps(result, ensure_ascii=False))
        new_count += 1

    month_str = date.today().strftime("%Y-%m")
    out_path = reflections_dir / f"{month_str}.jsonl"
    _atomic_append(out_path, new_lines)

    rollup = aggregate_brier(30, reflections_dir=reflections_dir)
    return {
        "new_reflections_count": new_count,
        "target_date": target.isoformat(),
        "brier_score_30d": rollup["score"],
        "brier_n_evaluations_30d": rollup["n"],
    }

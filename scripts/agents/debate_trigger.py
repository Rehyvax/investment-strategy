"""Debate trigger logic — decides if a Bull vs Bear debate should
run for a given ticker, plus persistence helpers for the verdict +
transcript.

Triggers (first-match wins, evaluated in order):

    1. force=True                    → always run (user explicit ask)
    2. no prior debate ever          → run (first-debate)
    3. last debate older than N days → run (weekly_schedule, default 7d)
    4. high-relevance news in 24h    → run (news_high)
    5. otherwise                     → skip

Persisted under data/events/debates/{YYYY-MM}.jsonl with one event per
debate. Atomic append (.tmp + os.replace).
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

DEBATES_DIR = ROOT / "data" / "events" / "debates"
DEBATES_DIR.mkdir(parents=True, exist_ok=True)

WEEKLY_THRESHOLD_DAYS = 7


def _parse_iso_utc(s: str) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def get_last_debate(ticker: str, *, debates_dir: Path | None = None) -> dict[str, Any] | None:
    """Returns the most recent debate verdict for `ticker` from the
    current and previous month JSONL files. Returns None when the
    ticker has never been debated."""
    debates_dir = debates_dir or DEBATES_DIR
    if not debates_dir.exists():
        return None
    today = date.today()
    months = [today.strftime("%Y-%m")]
    if today.day < 8:
        prev = today.replace(day=1) - timedelta(days=1)
        months.append(prev.strftime("%Y-%m"))

    latest: dict[str, Any] | None = None
    latest_ts = ""
    for month_str in months:
        f = debates_dir / f"{month_str}.jsonl"
        if not f.exists():
            continue
        with f.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("ticker") != ticker:
                    continue
                ts = entry.get("timestamp", "")
                if ts > latest_ts:
                    latest = entry
                    latest_ts = ts
    return latest


def should_run_debate(
    ticker: str,
    cerebro_state: dict[str, Any] | None = None,
    *,
    force: bool = False,
    debates_dir: Path | None = None,
    threshold_days: int = WEEKLY_THRESHOLD_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Returns `{"trigger": bool, "reason": str, ...}`.

    `cerebro_state` may be None when called outside the runner (e.g.
    tests); the news_high trigger then skips silently."""
    now_dt = now or datetime.now(timezone.utc)

    if force:
        return {"trigger": True, "reason": "user_force"}

    last = get_last_debate(ticker, debates_dir=debates_dir)
    if last is None:
        return {"trigger": True, "reason": "first_debate"}

    last_dt = _parse_iso_utc(last.get("timestamp", ""))
    if last_dt is not None:
        days_since = (now_dt - last_dt).days
        if days_since >= threshold_days:
            return {
                "trigger": True,
                "reason": "weekly_schedule",
                "days_since_last": days_since,
            }

    news_items = (cerebro_state or {}).get("news_by_asset", {}).get(ticker, [])
    cutoff_24h = (now_dt - timedelta(days=1)).isoformat()
    recent_high = [
        n for n in news_items
        if n.get("relevance") == "high"
        and (n.get("timestamp") or "") > cutoff_24h
    ]
    if recent_high:
        return {
            "trigger": True,
            "reason": "news_high",
            "evidence": [n.get("headline") for n in recent_high[:3]],
        }

    return {"trigger": False, "reason": "no_trigger"}


def persist_debate(
    ticker: str,
    debate_result: dict[str, Any],
    trigger_reason: str,
    *,
    debates_dir: Path | None = None,
    now: datetime | None = None,
) -> str:
    """Atomically append a debate event. Returns the path of the file
    that received the new line."""
    debates_dir = debates_dir or DEBATES_DIR
    debates_dir.mkdir(parents=True, exist_ok=True)
    now_dt = now or datetime.now(timezone.utc)
    month_str = now_dt.strftime("%Y-%m")
    file_path = debates_dir / f"{month_str}.jsonl"

    entry: dict[str, Any] = {
        "ticker": ticker,
        "timestamp": now_dt.isoformat().replace("+00:00", "Z"),
        "trigger_reason": trigger_reason,
        **debate_result,
    }

    existing = (
        file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    )
    if existing and not existing.endswith("\n"):
        existing += "\n"
    body = existing + json.dumps(entry, ensure_ascii=False) + "\n"

    tmp = file_path.with_suffix(".jsonl.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, file_path)
    return str(file_path)

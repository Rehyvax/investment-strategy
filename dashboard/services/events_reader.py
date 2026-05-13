"""Reads decision/run events from data/events/*.jsonl for the dashboard.

Strict read-only. Future phases (news feed live, decision audit screen)
will consume from here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

LAB_ROOT = Path(__file__).resolve().parents[2]
EVENTS_DIR = LAB_ROOT / "data" / "events"


def iter_jsonl(rel_path: str) -> Iterator[dict[str, Any]]:
    path = EVENTS_DIR / rel_path
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

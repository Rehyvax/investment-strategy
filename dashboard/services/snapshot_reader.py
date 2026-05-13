"""Reads portfolio snapshots from data/snapshots/{portfolio_id}/*.json.

Snapshots are produced by `src.portfolios.snapshot.SnapshotRebuilder`
and live outside the dashboard tree (per gitignored `data/` principle).
This reader is the boundary between dashboard UI and the lab's
canonical event store.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

# Lab root is three levels up from this file:
# dashboard/services/snapshot_reader.py -> investment-strategy/
LAB_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS_DIR = LAB_ROOT / "data" / "snapshots"


def load_snapshot(portfolio_id: str, as_of: date) -> dict[str, Any] | None:
    path = SNAPSHOTS_DIR / portfolio_id / f"{as_of.isoformat()}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def latest_snapshot(portfolio_id: str) -> dict[str, Any] | None:
    pdir = SNAPSHOTS_DIR / portfolio_id
    if not pdir.exists():
        return None
    files = sorted(pdir.glob("*.json"))
    if not files:
        return None
    with files[-1].open("r", encoding="utf-8") as fp:
        return json.load(fp)

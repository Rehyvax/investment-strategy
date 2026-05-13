"""Reads positions from the latest real-portfolio snapshot.

Adapted to the rebuilder schema:
- field is `quantity` (not `shares`).
- value field is `current_value_eur`, cost is `cost_basis_eur` (no
  `cost_basis_total_eur` in v1 rebuilder).
- weight_pct is NOT propagated by rebuilder; compute from
  `current_value_eur / nav_total_eur * 100`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS_DIR = LAB_ROOT / "data" / "snapshots"


class PositionReader:
    def __init__(self, snapshots_dir: Path | None = None):
        self.snapshots_dir = snapshots_dir or SNAPSHOTS_DIR

    def get_latest_snapshot(
        self, portfolio_id: str = "real"
    ) -> dict[str, Any] | None:
        pdir = self.snapshots_dir / portfolio_id
        if not pdir.exists():
            return None
        snaps: list[Path] = []
        for f in pdir.glob("*.json"):
            if f.name.startswith("_"):
                continue
            stem = f.stem
            if (
                len(stem) == 10
                and stem[4] == "-"
                and stem[7] == "-"
            ):
                snaps.append(f)
        if not snaps:
            return None
        snaps.sort()  # ascending by date string
        with snaps[-1].open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def get_position(
        self, ticker: str, portfolio_id: str = "real"
    ) -> dict[str, Any] | None:
        snap = self.get_latest_snapshot(portfolio_id)
        if not snap:
            return None
        nav = float(snap.get("nav_total_eur", 0.0))
        for p in snap.get("positions", []) or []:
            if p.get("ticker") == ticker:
                # Augment with computed weight_pct if missing.
                weight = p.get("weight_pct")
                if weight is None and nav > 0:
                    cv = p.get("current_value_eur", 0.0)
                    weight = (cv / nav) * 100.0
                return {**p, "weight_pct": weight or 0.0, "_nav_total_eur": nav}
        return None

    def list_assets(self, portfolio_id: str = "real") -> list[str]:
        snap = self.get_latest_snapshot(portfolio_id)
        if not snap:
            return []
        return [
            p.get("ticker")
            for p in snap.get("positions", []) or []
            if p.get("ticker")
        ]

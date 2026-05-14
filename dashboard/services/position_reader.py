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
# Cloud fallback (only for portfolio_id == "real"). Mirrors the latest
# dated snapshot under data/snapshots/real/, sanitized — see
# scripts/generate_cerebro_state.py::_sanitize_real_snapshot.
SANITIZED_REAL_FP = (
    LAB_ROOT / "dashboard" / "data" / "snapshot_real_latest.json"
)


class PositionReader:
    def __init__(
        self,
        snapshots_dir: Path | None = None,
        sanitized_real_fp: Path | None = None,
    ):
        self.snapshots_dir = snapshots_dir or SNAPSHOTS_DIR
        self.sanitized_real_fp = sanitized_real_fp or SANITIZED_REAL_FP

    def get_latest_snapshot(
        self, portfolio_id: str = "real"
    ) -> dict[str, Any] | None:
        pdir = self.snapshots_dir / portfolio_id
        if pdir.exists():
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
            if snaps:
                snaps.sort()  # ascending by date string
                try:
                    with snaps[-1].open("r", encoding="utf-8") as fp:
                        return json.load(fp)
                except (OSError, json.JSONDecodeError):
                    pass
        if portfolio_id == "real" and self.sanitized_real_fp.exists():
            try:
                return json.loads(
                    self.sanitized_real_fp.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                return None
        return None

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

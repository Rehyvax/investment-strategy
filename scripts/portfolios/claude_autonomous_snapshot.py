"""Claude Autonomous daily snapshot — captures Alpaca account state to
data/snapshots/claude_autonomous/{YYYY-MM-DD}.json so the comparator,
risk metrics, and Pantalla 11 share the same loaders as every other
portfolio in the lab.

Field shape mirrors the synthetic benchmark snapshots:
- nav_total_eur: USD equity (kept as 'eur' field for cross-loader compat)
- positions[]: ticker, shares, cost_basis_per_share, current_price_native,
  current_value_eur, weight_pct, unrealized_pl, unrealized_plpc

Idempotent: skips if today's snapshot already exists.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SNAP_DIR = ROOT / "data" / "snapshots" / "claude_autonomous"

logger = logging.getLogger(__name__)


def update_claude_autonomous_snapshot(
    target_date: date | None = None, *, force: bool = False
) -> Path | None:
    from scripts.alpaca.client import (  # local import for isolation
        alpaca_available,
        get_account_summary,
        get_positions,
    )

    target_date = target_date or date.today()
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SNAP_DIR / f"{target_date.isoformat()}.json"
    if snap_path.exists() and not force:
        return snap_path
    if not alpaca_available():
        logger.info("Alpaca unavailable — skipping autonomous snapshot")
        return None
    account = get_account_summary()
    if account is None:
        return None
    positions = get_positions()
    equity = float(account["equity"])
    snapshot = {
        "as_of_date": target_date.isoformat(),
        "portfolio_id": "claude_autonomous",
        "nav_total_eur": equity,                    # USD equity, field name kept for compat
        "cash_eur": float(account["cash"]),
        "currency_base": account.get("currency", "USD"),
        "alpaca_account_number": account.get("account_number"),
        "alpaca_status": account.get("status"),
        "positions": [
            {
                "ticker": p["ticker"],
                "shares": p["shares"],
                "cost_basis_per_share_native": p["avg_entry_price"],
                "current_price_native": p["current_price"],
                "current_value_eur": p["market_value"],
                "weight_pct": (
                    (p["market_value"] / equity * 100.0) if equity > 0 else 0.0
                ),
                "unrealized_pl": p["unrealized_pl"],
                "unrealized_plpc": p["unrealized_plpc"],
                "currency": "USD",
            }
            for p in positions
        ],
    }
    snap_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snap_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = update_claude_autonomous_snapshot(force=True)
    print(f"Claude Autonomous snapshot: {p}")

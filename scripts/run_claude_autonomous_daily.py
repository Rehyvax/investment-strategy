"""Daily runner for the Claude Autonomous experiment.

Cron: weekdays 15:30 ES (post US-market open). Steps:
  1. Verify Alpaca account reachable.
  2. Load cerebro_state for today's market context.
  3. Run `make_autonomous_decision` (LLM call + optional trades).
  4. Snapshot Alpaca state to data/snapshots/claude_autonomous/.

Exit code 0 on success, 1 on any blocker.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Python auto-adds the script's parent dir to sys.path[0] when invoked
# as `python scripts/run_claude_autonomous_daily.py`. That dir is
# `.../scripts`, which causes `import alpaca` to resolve to our
# `scripts/alpaca/` package and shadow the alpaca-py SDK. Strip it.
_SCRIPTS_DIR = str(ROOT / "scripts")
sys.path[:] = [p for p in sys.path if p and Path(p).resolve() != Path(_SCRIPTS_DIR).resolve()]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from scripts.agents.claude_autonomous import make_autonomous_decision  # noqa: E402
from scripts.alpaca.client import alpaca_available, get_account_summary  # noqa: E402
from scripts.portfolios.claude_autonomous_snapshot import (  # noqa: E402
    update_claude_autonomous_snapshot,
)

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
CEREBRO_PATH = ROOT / "dashboard" / "data" / "cerebro_state.json"

logger = logging.getLogger("claude_autonomous_daily")


def _configure_logger() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        LOGS_DIR / "claude_autonomous_daily.log", encoding="utf-8"
    )
    sh = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


def main(argv: list[str] | None = None) -> int:
    _configure_logger()
    p = argparse.ArgumentParser(
        description="Daily Claude Autonomous decision + snapshot."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "LLM call still happens (real cost ~$0.50-2) but no Alpaca "
            "orders are submitted."
        ),
    )
    args = p.parse_args(argv)

    if not alpaca_available():
        logger.error("Alpaca unavailable (missing keys or SDK).")
        return 1
    account = get_account_summary()
    if account is None:
        logger.error("Could not fetch Alpaca account.")
        return 1
    logger.info(
        f"Alpaca OK: account={account.get('account_number')} "
        f"equity=${account['equity']:,.2f} cash=${account['cash']:,.2f}"
    )

    cerebro_state: dict = {}
    if CEREBRO_PATH.exists():
        try:
            cerebro_state = json.loads(
                CEREBRO_PATH.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"cerebro_state load failed: {exc}")

    decision = make_autonomous_decision(
        cerebro_state, dry_run=args.dry_run
    )
    if decision is None:
        logger.error("Decision failed.")
        return 1
    logger.info(
        f"Decision: type={decision.get('decision_type')} "
        f"trades={len(decision.get('trades') or [])} "
        f"horizon={decision.get('expected_horizon_days')}d "
        f"risk={decision.get('self_assessed_risk')}"
    )
    if decision.get("decision_type") == "trade":
        for t in decision.get("trades") or []:
            order = t.get("order_result")
            status = (order or {}).get("status", "skipped")
            logger.info(
                f"  {t.get('action', '?').upper()} {t.get('qty', '?')} "
                f"{t.get('ticker', '?')} -> {status}"
            )

    # Brief pause for orders to settle, then snapshot.
    if decision.get("decision_type") == "trade" and not args.dry_run:
        time.sleep(3)
    snap_path = update_claude_autonomous_snapshot(force=True)
    if snap_path:
        logger.info(f"Snapshot updated: {snap_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

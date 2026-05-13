"""Weekly debate runner.

Walks the latest real-portfolio snapshot and for each held ticker
decides (via `debate_trigger.should_run_debate`) whether to invoke the
LangGraph Bull/Bear debate. Persists each verdict + transcript via
`debate_trigger.persist_debate`.

CLI:
    python scripts/run_weekly_debates.py
        Run for every position in the real snapshot.

    python scripts/run_weekly_debates.py --force --ticker MSFT
        Force a single debate on MSFT (skips trigger logic).

    python scripts/run_weekly_debates.py --max-tickers 3
        Cap the number of debates this run (cost control).

    python scripts/run_weekly_debates.py --max-rounds 1
        Single-round debate (cheaper, less depth). Default 2.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dashboard"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from scripts.agents.debate_trigger import (  # noqa: E402
    persist_debate,
    should_run_debate,
)
from scripts.agents.graph import run_debate  # noqa: E402

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

CEREBRO_PATH = ROOT / "dashboard" / "data" / "cerebro_state.json"
SNAPSHOT_DIR = ROOT / "data" / "snapshots" / "real"


logger = logging.getLogger("weekly_debates")


def _configure_logger() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        LOGS_DIR / "weekly_debates.log", encoding="utf-8"
    )
    sh = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


def _load_latest_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT_DIR.exists():
        return None
    candidates: list[Path] = []
    for f in SNAPSHOT_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            candidates.append(f)
    if not candidates:
        return None
    candidates.sort()
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def _load_cerebro_state() -> dict[str, Any]:
    if CEREBRO_PATH.exists():
        try:
            return json.loads(CEREBRO_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def build_ticker_data(
    ticker: str,
    cerebro_state: dict[str, Any],
    position: dict[str, Any],
    *,
    thesis: dict[str, Any] | None = None,
    falsifiers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the dict consumed by the bull/bear/facilitator agents."""
    cb_per_share = float(position.get("cost_basis_per_share_native") or 0.0)
    if cb_per_share == 0.0:
        # Fallback: derive from total cost basis / quantity.
        qty = float(position.get("quantity") or 0.0)
        cb_total = float(position.get("cost_basis_native") or 0.0)
        cb_per_share = cb_total / qty if qty else 0.0
    current_price = float(position.get("current_price_native") or 0.0)
    pnl_pct = (
        ((current_price / cb_per_share) - 1.0) * 100.0
        if cb_per_share > 0
        else 0.0
    )

    data: dict[str, Any] = {
        "ticker": ticker,
        "weight_pct": float(position.get("weight_pct") or 0.0),
        "position_eur": float(position.get("current_value_eur") or 0.0),
        "current_price": current_price,
        "cost_basis": cb_per_share,
        "currency": position.get("currency", "USD"),
        "pnl_pct": pnl_pct,
        "thesis_summary": "Sin tesis formal registrada para este ticker.",
        "thesis_status": "no_thesis",
        "verdict": "no_thesis",
        "falsifiers": falsifiers or [],
        "technicals": cerebro_state.get("technicals_by_asset", {}).get(ticker, {}),
        "fundamentals": cerebro_state.get("fundamentals_by_asset", {}).get(ticker, {}),
        "news": cerebro_state.get("news_by_asset", {}).get(ticker, []),
    }
    if thesis is not None:
        summary_src = (
            thesis.get("note")
            or thesis.get("confidence_justification")
            or thesis.get("reasoning")
            or thesis.get("thesis_summary")
            or ""
        )
        if isinstance(summary_src, dict):
            summary_src = json.dumps(summary_src)[:400]
        data["thesis_summary"] = (str(summary_src) or "—")[:400]
        data["thesis_status"] = (
            thesis.get("event_type", "thesis").replace("_", " ")
        )
        data["verdict"] = (
            thesis.get("recommendation")
            or thesis.get("recommendation_v2")
            or "watch"
        )
    return data


def _resolve_thesis(ticker: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Use the dashboard ThesisReader so we honor closed-position
    semantics (AXON, etc.). Imported lazily to avoid pulling Streamlit
    at import time."""
    from services.thesis_reader import ThesisReader  # noqa: WPS433

    tr = ThesisReader()
    thesis = tr.get_authoritative_version(ticker)
    falsifiers = tr.get_falsifier_status(thesis) if thesis else []
    return thesis, falsifiers


def main(argv: list[str] | None = None) -> int:
    _configure_logger()
    parser = argparse.ArgumentParser(description="Weekly Bull/Bear debate runner.")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Run for a single ticker (else: all positions).")
    parser.add_argument("--force", action="store_true",
                        help="Skip trigger checks (always run).")
    parser.add_argument("--max-tickers", type=int, default=None,
                        help="Cap the number of debates this run.")
    parser.add_argument("--max-rounds", type=int, default=2,
                        help="Number of rebuttal rounds (default 2).")
    args = parser.parse_args(argv)

    snapshot = _load_latest_snapshot()
    if snapshot is None:
        logger.error("No snapshot found in data/snapshots/real/")
        return 1
    cerebro_state = _load_cerebro_state()

    positions = snapshot.get("positions", []) or []
    if args.ticker:
        positions = [p for p in positions if p.get("ticker") == args.ticker]
        if not positions:
            logger.error(f"Ticker {args.ticker} not in latest snapshot")
            return 1
    if args.max_tickers is not None:
        positions = positions[: args.max_tickers]

    debates_run = 0
    debates_skipped = 0
    for pos in positions:
        ticker = pos.get("ticker")
        if not ticker:
            continue

        decision = should_run_debate(
            ticker, cerebro_state, force=args.force
        )
        if not decision.get("trigger"):
            logger.info(f"{ticker}: skip ({decision.get('reason')})")
            debates_skipped += 1
            continue

        logger.info(f"{ticker}: run ({decision.get('reason')})")
        thesis, falsifiers = _resolve_thesis(ticker)
        ticker_data = build_ticker_data(
            ticker, cerebro_state, pos, thesis=thesis, falsifiers=falsifiers
        )

        result = run_debate(ticker_data, max_rounds=args.max_rounds)
        out_path = persist_debate(ticker, result, decision.get("reason", "unknown"))
        debates_run += 1
        logger.info(
            f"{ticker}: verdict={result.get('verdict', '?')} "
            f"action={result.get('suggested_action', '?')} "
            f"weight={result.get('weight', '?')} "
            f"-> {out_path}"
        )

    logger.info(f"Done: {debates_run} run, {debates_skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Daily reflection runner.

Walks debates from `lookforward_days` ago (default 7) and computes a
realized-vs-predicted reflection per debate. Idempotent: debates that
already have a reflection are skipped.

CLI:
    python scripts/run_daily_reflections.py
    python scripts/run_daily_reflections.py --lookforward 14
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from scripts.agents.reflection import run_reflections  # noqa: E402

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("daily_reflections")


def _configure_logger() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        LOGS_DIR / "daily_reflections.log", encoding="utf-8"
    )
    sh = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


def main(argv: list[str] | None = None) -> int:
    _configure_logger()
    p = argparse.ArgumentParser(description="Daily reflection runner.")
    p.add_argument(
        "--lookforward",
        type=int,
        default=7,
        help="Days between debate and reflection (default 7).",
    )
    args = p.parse_args(argv)

    summary = run_reflections(lookforward_days=args.lookforward)
    logger.info(
        f"Reflections: new={summary['new_reflections_count']} "
        f"target_date={summary['target_date']} "
        f"brier_30d={summary['brier_score_30d']} "
        f"n_30d={summary['brier_n_evaluations_30d']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

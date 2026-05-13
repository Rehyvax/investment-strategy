"""Convenience wrapper around src.portfolios.price_log.PriceLog for the
dashboard. Lets pages import without reaching across `src/` directly."""

from __future__ import annotations

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from src.portfolios.price_log import PriceLog  # noqa: E402


def get_price_log() -> PriceLog:
    return PriceLog()

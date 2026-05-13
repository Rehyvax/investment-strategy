"""Tests for `scripts/mercado_ai.py` — pure context builders + chat
no-LLM fallback. No network or LLM calls."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mercado_ai as mai  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _snapshot(n_positions: int = 3) -> dict:
    positions = [
        {
            "ticker": f"T{i}",
            "sector_at_purchase": "Tech",
            "country_at_purchase": "United States",
            "current_value_eur": 1000.0 * (i + 1),
            "cost_basis_per_share_native": 100.0,
            "current_price_native": 100.0 + i,
        }
        for i in range(n_positions)
    ]
    return {
        "as_of_date": "2026-05-14",
        "nav_total_eur": 50000.0,
        "cash_eur": 1000.0,
        "positions": positions,
    }


def _cerebro(with_extras: bool = True) -> dict:
    base = {
        "recommendations": [
            {"asset": "T0", "type": "WATCH", "priority": "high"},
        ],
        "debates_by_asset": {
            "T0": {
                "verdict": "thesis_neutral",
                "timestamp": "2026-05-14T01:07:00Z",
                "suggested_action": "monitor",
                "confidence": "medium",
            }
        },
    } if with_extras else {}
    base["news_by_asset"] = {
        "T0": [
            {
                "relevance": "high",
                "summary_1line": "Earnings beat",
                "headline": "Earnings beat",
            }
        ]
    }
    base["technicals_by_asset"] = {
        "T0": {
            "trend": "bullish_mild",
            "rsi14": 65,
            "rsi_signal": "strong_momentum",
            "macd_signal": "bullish_momentum",
            "bb_position": "upper_half",
        }
    }
    base["fundamentals_by_asset"] = {
        "T0": {
            "pe_ratio": 25.0,
            "operating_margin": 0.15,
            "revenue_growth": 0.10,
            "target_mean_price": 150.0,
            "recommendation_key": "buy",
            "flags": ["high_pe"],
        }
    }
    base["market_state"] = {
        "explanation": "Risk-on moderado. VIX 15 en zona calmada."
    }
    base["brier_score_30d"] = 0.65
    base["brier_n_evaluations_30d"] = 12
    return base


# ---------------------------------------------------------------------------
# Context summary
# ---------------------------------------------------------------------------
class TestBuildContextSummary:
    def test_includes_kpis(self):
        snap = _snapshot(3)
        cerebro = _cerebro()
        out = mai.build_context_summary(cerebro, snap)
        assert "NAV €50,000" in out
        assert "cash €1,000" in out
        assert "3 posiciones" in out
        assert "Brier 30d: 0.650" in out
        assert "Recommendations" in out

    def test_caps_positions_to_25(self):
        snap = _snapshot(40)
        out = mai.build_context_summary({}, snap)
        # Count lines starting with "  T" (position lines)
        position_lines = [
            ln for ln in out.split("\n")
            if ln.lstrip().startswith("T") and "|" in ln
        ]
        assert len(position_lines) == 25


# ---------------------------------------------------------------------------
# Asset detail
# ---------------------------------------------------------------------------
class TestBuildAssetDetail:
    def test_includes_news_when_available(self):
        out = mai.build_asset_detail(_cerebro(), "T0")
        assert "[HIGH] Earnings beat" in out

    def test_includes_technicals_and_fundamentals(self):
        out = mai.build_asset_detail(_cerebro(), "T0")
        assert "Technicals" in out
        assert "trend=bullish_mild" in out
        assert "Fundamentals" in out
        assert "P/E=25.0" in out
        assert "Red flags: high_pe" in out

    def test_includes_debate_when_available(self):
        out = mai.build_asset_detail(_cerebro(), "T0")
        assert "Último debate" in out
        assert "thesis_neutral" in out


# ---------------------------------------------------------------------------
# Ticker extraction (word-boundary)
# ---------------------------------------------------------------------------
class TestExtractTickers:
    def test_finds_exact_token(self):
        msg = "Compara MSFT vs MELI en fundamentals"
        out = mai.extract_tickers_mentioned(msg, ["MSFT", "MELI", "AAPL"])
        assert set(out) == {"MSFT", "MELI"}

    def test_ignores_substring_match(self):
        # BAC must NOT match inside "back" or "BACKUP"
        msg = "Voy a hacer un BACKUP de mi base de datos"
        out = mai.extract_tickers_mentioned(msg, ["BAC", "BCS"])
        assert out == []

    def test_caps_at_max_tickers(self):
        msg = "T0 T1 T2 T3 T4 T5 T6 T7"
        all_t = [f"T{i}" for i in range(8)]
        out = mai.extract_tickers_mentioned(msg, all_t)
        assert len(out) <= mai.MAX_TICKERS_DETAIL


# ---------------------------------------------------------------------------
# Chat entry — no-LLM path
# ---------------------------------------------------------------------------
class TestChatNoLLM:
    def test_returns_none_when_client_absent(self, monkeypatch):
        monkeypatch.setattr(mai, "get_client", lambda: None)
        out = mai.chat_mercado_ai(
            "¿Cómo está MSFT?", [], _cerebro(), _snapshot()
        )
        assert out is None

"""Tests for `scripts/agents/reflection.py`.

The pure helpers (`expected_direction_from_verdict`, `brier_correct`,
`aggregate_brier`) test without I/O. End-to-end `reflect_on_debate`
and `run_reflections` exercise dependency injection (custom
`fetch_returns_fn` + `fetch_spy_fn`) so no yfinance call is made and
no LLM call is burnt."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.agents import reflection as refl  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestExpectedDirection:
    def test_exit_maps_to_down(self):
        assert refl.expected_direction_from_verdict(
            {"suggested_action": "exit", "verdict": "thesis_weakened"}
        ) == "down"

    def test_reduce_maps_to_down(self):
        assert refl.expected_direction_from_verdict(
            {"suggested_action": "reduce", "verdict": "thesis_neutral"}
        ) == "down"

    def test_invalidated_verdict_maps_to_down(self):
        assert refl.expected_direction_from_verdict(
            {"suggested_action": "maintain", "verdict": "thesis_invalidated"}
        ) == "down"

    def test_maintain_maps_to_up(self):
        assert refl.expected_direction_from_verdict(
            {"suggested_action": "maintain", "verdict": "thesis_strengthened"}
        ) == "up"


class TestBrierCorrect:
    def test_match_returns_one(self):
        assert refl.brier_correct("up", "up") == 1
        assert refl.brier_correct("down", "down") == 1

    def test_mismatch_returns_zero(self):
        assert refl.brier_correct("up", "down") == 0
        assert refl.brier_correct("down", "up") == 0


# ---------------------------------------------------------------------------
# reflect_on_debate — injected fetchers, no network
# ---------------------------------------------------------------------------
class TestReflectOnDebate:
    def _debate(self, suggested: str = "maintain", verdict: str = "thesis_strengthened") -> dict:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "ticker": "MOCK",
            "timestamp": ts,
            "verdict": verdict,
            "suggested_action": suggested,
            "confidence": "medium",
            "bull_rounds": ["bull arg"],
            "bear_rounds": ["bear arg"],
        }

    def test_correct_when_predicted_up_and_realized_up(self, monkeypatch):
        monkeypatch.setattr(refl, "get_client", lambda: None)
        result = refl.reflect_on_debate(
            self._debate(suggested="maintain"),
            lookforward_days=5,
            fetch_returns_fn=lambda *_a, **_k: {
                "from_price": 100, "to_price": 105, "raw_return_pct": 5.0
            },
            fetch_spy_fn=lambda *_a, **_k: 1.0,
        )
        assert result is not None
        assert result["expected_direction"] == "up"
        assert result["actual_direction"] == "up"
        assert result["brier_correct"] == 1
        assert result["realized_return_pct"] == 5.0
        assert result["alpha_vs_spy_pct"] == 4.0

    def test_correct_when_predicted_down_and_realized_down(self, monkeypatch):
        monkeypatch.setattr(refl, "get_client", lambda: None)
        result = refl.reflect_on_debate(
            self._debate(suggested="exit", verdict="thesis_invalidated"),
            lookforward_days=5,
            fetch_returns_fn=lambda *_a, **_k: {
                "from_price": 100, "to_price": 92, "raw_return_pct": -8.0
            },
            fetch_spy_fn=lambda *_a, **_k: 0.5,
        )
        assert result["expected_direction"] == "down"
        assert result["actual_direction"] == "down"
        assert result["brier_correct"] == 1

    def test_returns_none_on_no_data(self, monkeypatch):
        monkeypatch.setattr(refl, "get_client", lambda: None)
        result = refl.reflect_on_debate(
            self._debate(),
            fetch_returns_fn=lambda *_a, **_k: None,
            fetch_spy_fn=lambda *_a, **_k: None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Aggregate Brier + run_reflections walk
# ---------------------------------------------------------------------------
class TestAggregateBrierAndRun:
    def test_aggregate_returns_none_when_no_reflections(self, tmp_path):
        out = refl.aggregate_brier(days=30, reflections_dir=tmp_path)
        assert out["score"] is None
        assert out["n"] == 0

    def test_aggregate_computes_average(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        f = tmp_path / "2026-05.jsonl"
        f.write_text(
            "\n".join(
                json.dumps(
                    {
                        "ticker": f"X{i}",
                        "debate_timestamp": now,
                        "reflection_timestamp": now,
                        "brier_correct": v,
                    }
                )
                for i, v in enumerate([1, 1, 0, 1, 0])
            ) + "\n",
            encoding="utf-8",
        )
        out = refl.aggregate_brier(days=30, reflections_dir=tmp_path)
        assert out["n"] == 5
        assert out["score"] == 0.6  # 3/5

    def test_run_reflections_skips_existing(self, tmp_path, monkeypatch):
        # Set up directories
        debates_dir = tmp_path / "debates"
        reflections_dir = tmp_path / "reflections"
        debates_dir.mkdir()
        reflections_dir.mkdir()

        # Seed a debate from 7 days ago
        old = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).replace(microsecond=0)
        ts = old.isoformat().replace("+00:00", "Z")
        month = old.strftime("%Y-%m")
        (debates_dir / f"{month}.jsonl").write_text(
            json.dumps(
                {
                    "ticker": "MOCK",
                    "timestamp": ts,
                    "verdict": "thesis_neutral",
                    "suggested_action": "maintain",
                    "bull_rounds": ["b"],
                    "bear_rounds": ["B"],
                }
            ) + "\n",
            encoding="utf-8",
        )
        # Seed an existing reflection for the same key.
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        existing = {
            "ticker": "MOCK",
            "debate_timestamp": ts,
            "reflection_timestamp": now_iso,
            "brier_correct": 1,
        }
        cur_month = date.today().strftime("%Y-%m")
        (reflections_dir / f"{cur_month}.jsonl").write_text(
            json.dumps(existing) + "\n", encoding="utf-8"
        )

        monkeypatch.setattr(refl, "get_client", lambda: None)
        # Force-include any test fetcher even though we don't expect a
        # call (the existing reflection should make us skip).
        out = refl.run_reflections(
            target_date=old.date(),
            lookforward_days=7,
            debates_dir=debates_dir,
            reflections_dir=reflections_dir,
        )
        assert out["new_reflections_count"] == 0

"""Tests for the Bull/Bear debate agents + LangGraph orchestration +
trigger logic. All LLM paths are exercised through the no-client
fallback so the suite never burns tokens."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.agents import (  # noqa: E402
    bear_researcher,
    bull_researcher,
    debate_facilitator,
    debate_trigger,
    graph,
)


# ---------------------------------------------------------------------------
# Bull / Bear initial argument — no-client fallback
# ---------------------------------------------------------------------------
class TestBullInitialNoLLM:
    def test_returns_none_when_client_absent(self, monkeypatch):
        monkeypatch.setattr(bull_researcher, "get_client", lambda: None)
        out = bull_researcher.bull_initial_argument({"ticker": "MSFT"})
        assert out is None


class TestBearInitialNoLLM:
    def test_returns_none_when_client_absent(self, monkeypatch):
        monkeypatch.setattr(bear_researcher, "get_client", lambda: None)
        out = bear_researcher.bear_initial_argument({"ticker": "MSFT"})
        assert out is None


# ---------------------------------------------------------------------------
# Facilitator — defensive parser
# ---------------------------------------------------------------------------
class TestFacilitatorParser:
    def test_parses_clean_json_then_reasoning(self):
        text = (
            '{"verdict":"thesis_strengthened","weight":"bull_wins",'
            '"key_evidence_for_verdict":"Q1 beat","key_trigger_to_monitor":"Q2 margins",'
            '"suggested_action":"maintain","confidence":"high"}\n'
            "Bull case dominated because Q1 print was clean and management "
            "guidance held."
        )
        out = debate_facilitator.parse_facilitator_response(text)
        assert out["verdict"] == "thesis_strengthened"
        assert out["weight"] == "bull_wins"
        assert out["confidence"] == "high"
        assert out["suggested_action"] == "maintain"
        assert "Q1 print" in out["reasoning"]

    def test_strips_markdown_fence(self):
        text = (
            "```json\n"
            '{"verdict":"thesis_weakened","weight":"bear_wins","suggested_action":"reduce","confidence":"medium"}\n'
            "```\n"
            "Reasoning paragraph here."
        )
        out = debate_facilitator.parse_facilitator_response(text)
        assert out["verdict"] == "thesis_weakened"
        assert out["weight"] == "bear_wins"

    def test_falls_back_on_invalid_json(self):
        out = debate_facilitator.parse_facilitator_response("not json at all")
        assert out["verdict"] == "thesis_neutral"
        assert out["confidence"] == "low"
        assert out.get("_parse_error") == "json_decode_failed"

    def test_unknown_verdict_falls_back_to_neutral(self):
        text = '{"verdict":"thesis_amazing","weight":"bull_wins","suggested_action":"maintain","confidence":"high"}\n'
        out = debate_facilitator.parse_facilitator_response(text)
        assert out["verdict"] == "thesis_neutral"  # not in enum → defaulted

    def test_facilitate_debate_returns_none_without_client(self, monkeypatch):
        monkeypatch.setattr(debate_facilitator, "get_client", lambda: None)
        out = debate_facilitator.facilitate_debate(
            {"ticker": "X"}, ["bull arg"], ["bear arg"]
        )
        assert out is None


# ---------------------------------------------------------------------------
# LangGraph state accumulation — no-LLM mode
# ---------------------------------------------------------------------------
class TestDebateStateAccumulates:
    def test_run_debate_produces_transcripts_even_without_llm(self, monkeypatch):
        # Force every LLM call to return None — graph should still
        # complete with placeholder strings.
        monkeypatch.setattr(graph, "bull_initial_argument", lambda _: None)
        monkeypatch.setattr(graph, "bear_initial_argument", lambda _: None)
        monkeypatch.setattr(
            graph, "bull_rebuttal", lambda _, **__: None
        )
        monkeypatch.setattr(
            graph, "bear_rebuttal", lambda _, **__: None
        )
        monkeypatch.setattr(graph, "facilitate_debate", lambda *_args, **_k: None)

        result = graph.run_debate({"ticker": "MOCK"}, max_rounds=2)
        # 2 rounds = bull_opening + 1 bull rebuttal = 2 bull rounds,
        # bear_opening + 1 bear rebuttal = 2 bear rounds.
        assert len(result["bull_rounds"]) == 2
        assert len(result["bear_rounds"]) == 2
        assert result["verdict"] == "thesis_neutral"
        assert result["confidence"] == "low"
        assert result.get("_facilitator_failed") is True


# ---------------------------------------------------------------------------
# Trigger logic
# ---------------------------------------------------------------------------
class TestShouldRunDebate:
    def test_force_always_runs(self, tmp_path):
        out = debate_trigger.should_run_debate(
            "MSFT", {}, force=True, debates_dir=tmp_path
        )
        assert out["trigger"] is True
        assert out["reason"] == "user_force"

    def test_first_debate_when_no_history(self, tmp_path):
        out = debate_trigger.should_run_debate(
            "MSFT", {}, debates_dir=tmp_path
        )
        assert out["trigger"] is True
        assert out["reason"] == "first_debate"

    def test_weekly_threshold_triggers(self, tmp_path):
        # Seed a debate from 8 days ago.
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=8)
        ).isoformat().replace("+00:00", "Z")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        f = tmp_path / f"{month}.jsonl"
        f.write_text(
            json.dumps({"ticker": "MSFT", "timestamp": old_ts}) + "\n",
            encoding="utf-8",
        )
        out = debate_trigger.should_run_debate(
            "MSFT", {}, debates_dir=tmp_path
        )
        assert out["trigger"] is True
        assert out["reason"] == "weekly_schedule"
        assert out["days_since_last"] >= 7

    def test_news_high_triggers_within_window(self, tmp_path):
        recent_ts = (
            datetime.now(timezone.utc) - timedelta(days=2)
        ).isoformat().replace("+00:00", "Z")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        f = tmp_path / f"{month}.jsonl"
        f.write_text(
            json.dumps({"ticker": "MSFT", "timestamp": recent_ts}) + "\n",
            encoding="utf-8",
        )
        news_ts = (
            datetime.now(timezone.utc) - timedelta(hours=4)
        ).isoformat().replace("+00:00", "Z")
        cerebro = {
            "news_by_asset": {
                "MSFT": [
                    {
                        "relevance": "high",
                        "headline": "Material news",
                        "timestamp": news_ts,
                    }
                ]
            }
        }
        out = debate_trigger.should_run_debate(
            "MSFT", cerebro, debates_dir=tmp_path
        )
        assert out["trigger"] is True
        assert out["reason"] == "news_high"
        assert "Material news" in (out.get("evidence") or [])

    def test_no_trigger_when_recent_and_no_news(self, tmp_path):
        recent_ts = (
            datetime.now(timezone.utc) - timedelta(days=3)
        ).isoformat().replace("+00:00", "Z")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        f = tmp_path / f"{month}.jsonl"
        f.write_text(
            json.dumps({"ticker": "MSFT", "timestamp": recent_ts}) + "\n",
            encoding="utf-8",
        )
        out = debate_trigger.should_run_debate(
            "MSFT", {}, debates_dir=tmp_path
        )
        assert out["trigger"] is False
        assert out["reason"] == "no_trigger"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class TestPersistDebate:
    def test_persist_debate_appends_atomic(self, tmp_path):
        verdict = {
            "verdict": "thesis_neutral",
            "suggested_action": "maintain",
            "bull_rounds": ["a"],
            "bear_rounds": ["b"],
        }
        path_str = debate_trigger.persist_debate(
            "MSFT", verdict, "user_force", debates_dir=tmp_path
        )
        assert Path(path_str).exists()
        lines = Path(path_str).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        ev = json.loads(lines[0])
        assert ev["ticker"] == "MSFT"
        assert ev["trigger_reason"] == "user_force"
        assert ev["verdict"] == "thesis_neutral"

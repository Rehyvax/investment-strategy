"""Tests for the Anthropic prompt-caching wrapper in llm_narratives.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import llm_narratives as ln  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers (no LLM call)
# ---------------------------------------------------------------------------
class TestCacheBlocks:
    def test_block_above_threshold_gets_cache_control(self):
        big = "x" * (ln._CACHE_MIN_CHARS + 10)
        out = ln._cache_blocks_to_anthropic_format([big])
        assert len(out) == 1
        assert out[0].get("cache_control") == {"type": "ephemeral"}

    def test_block_below_threshold_skips_cache_control(self):
        small = "tiny block"
        out = ln._cache_blocks_to_anthropic_format([small])
        assert len(out) == 1
        assert "cache_control" not in out[0]

    def test_empty_or_none_blocks_dropped(self):
        out = ln._cache_blocks_to_anthropic_format(["", None, "ok"])
        # `None` and "" are skipped; "ok" survives without cache_control.
        assert len(out) == 1
        assert out[0]["text"] == "ok"


# ---------------------------------------------------------------------------
# Usage tracker
# ---------------------------------------------------------------------------
class _FakeUsage:
    def __init__(
        self,
        input_tokens: int = 100,
        output_tokens: int = 50,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _FakeResponse:
    def __init__(self, usage: _FakeUsage) -> None:
        self.usage = usage


class TestUsagePersistence:
    def test_persist_writes_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ln, "_USAGE_DIR", tmp_path)
        usage = _FakeUsage(
            input_tokens=200,
            output_tokens=80,
            cache_read_input_tokens=1500,
        )
        result = ln._persist_usage(
            _FakeResponse(usage),
            caller="test",
            cached_blocks_count=1,
        )
        assert result["input_tokens"] == 200
        assert result["cache_read_input_tokens"] == 1500
        # File exists and is valid JSONL
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8").strip()
        entry = json.loads(content)
        assert entry["caller"] == "test"
        assert entry["cached_blocks_supplied"] == 1


class TestUsageRollup:
    def test_get_usage_today_aggregates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ln, "_USAGE_DIR", tmp_path)
        # Seed two entries from "today"
        from datetime import date, datetime, timezone
        f = tmp_path / f"{date.today().strftime('%Y-%m')}.jsonl"
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for k in [
            {"ts": ts, "caller": "a", "input_tokens": 100,
             "output_tokens": 50, "cache_creation_input_tokens": 1000,
             "cache_read_input_tokens": 0},
            {"ts": ts, "caller": "b", "input_tokens": 50,
             "output_tokens": 25, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 1000},
        ]:
            with f.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(k) + "\n")
        out = ln.get_usage_today()
        assert out["n_calls"] == 2
        assert out["input_tokens"] == 150
        assert out["cache_creation_input_tokens"] == 1000
        assert out["cache_read_input_tokens"] == 1000
        # cache_hit_rate = 1000 / (1000 + 1000) = 0.5
        assert out["cache_hit_rate"] == pytest.approx(0.5, abs=0.001)
        # Savings should be > 0 because cached reads cheaper than fresh inputs.
        assert out["estimated_savings_usd"] >= 0.0

    def test_get_usage_today_handles_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ln, "_USAGE_DIR", tmp_path)
        out = ln.get_usage_today()
        assert out["n_calls"] == 0
        assert out["cache_hit_rate"] is None


# ---------------------------------------------------------------------------
# call_llm_cached graceful degradation
# ---------------------------------------------------------------------------
class TestCallLLMCachedDegrades:
    def test_returns_none_when_client_absent(self, monkeypatch):
        monkeypatch.setattr(ln, "_get_client", lambda: None)
        out = ln.call_llm_cached(
            system_prompt="sys",
            user_prompt="hi",
            cache_blocks=["a"],
            caller="test",
        )
        assert out is None

"""Tests for the LLM narrative module.

These tests do not perform network calls. They exercise the
fallback-on-missing-key path and the API-error path (via monkeypatched
client) to verify the dashboard remains usable when the LLM is down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import llm_narratives as ln  # noqa: E402


class TestAvailability:
    def test_no_api_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert ln.is_llm_available() is False

    def test_with_api_key_returns_true(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        assert ln.is_llm_available() is True


class TestVixClassification:
    def test_unknown_when_none(self):
        assert ln._classify_vix(None) == "unknown"

    def test_buckets(self):
        assert ln._classify_vix(12) == "calmo (risk-on)"
        assert ln._classify_vix(17) == "neutral"
        assert ln._classify_vix(25) == "elevado (cautela)"
        assert ln._classify_vix(35) == "pánico (risk-off)"


class TestFallbackOnMissingKey:
    def test_market_state_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = ln.generate_market_state_narrative({}, {})
        assert result is None

    def test_comparative_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = ln.generate_comparative_narrative({})
        assert result is None

    def test_recommendation_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = ln.refine_recommendation_narrative({}, {})
        assert result is None


class _MockBlock:
    def __init__(self, text: str):
        self.text = text


class _MockResponse:
    def __init__(self, text: str):
        self.content = [_MockBlock(text)]


class _MockClient:
    def __init__(self, behavior: str = "success", text: str = "OK"):
        self.behavior = behavior
        self.text = text
        self.messages = self

    def create(self, **kwargs):  # noqa: ARG002 — mirror SDK signature
        if self.behavior == "raise":
            raise RuntimeError("simulated API error")
        return _MockResponse(self.text)


class TestErrorPathsWithMockClient:
    """Inject a mock client by replacing `_get_client`."""

    def test_market_state_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            ln, "_get_client", lambda: _MockClient(behavior="raise")
        )
        result = ln.generate_market_state_narrative(
            {"vix": 15.0}, {"nav_total_eur": 50000}
        )
        assert result is None

    def test_market_state_success(self, monkeypatch):
        monkeypatch.setattr(
            ln,
            "_get_client",
            lambda: _MockClient(
                behavior="success", text="Mercado neutral.  Sigue aguantando."
            ),
        )
        result = ln.generate_market_state_narrative(
            {"vix": 17.0, "bond_equity_ratio_30d": -0.05},
            {"nav_total_eur": 48000, "positions_count": 19},
        )
        assert result == "Mercado neutral.  Sigue aguantando."

    def test_comparative_splits_headline_and_narrative(self, monkeypatch):
        monkeypatch.setattr(
            ln,
            "_get_client",
            lambda: _MockClient(
                behavior="success",
                text="Tu cartera ha aguantado.\nLa diferencia es ruido en horizonte corto.",
            ),
        )
        result = ln.generate_comparative_narrative(
            {
                "nav_real": 48000,
                "delta_real_pct": -1.79,
                "comparator_today": "benchmark_passive",
                "diff_pp": -1.79,
            }
        )
        assert result is not None
        assert result["headline"] == "Tu cartera ha aguantado."
        assert "ruido" in result["narrative"]

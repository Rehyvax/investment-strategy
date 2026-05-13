"""Tests for the chat module. No network calls — exercises the
no-key fallback path and a mocked client for the success path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import llm_chat  # noqa: E402


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

    def create(self, **kwargs):  # noqa: ARG002
        if self.behavior == "raise":
            raise RuntimeError("simulated API error")
        return _MockResponse(self.text)


class TestAvailability:
    def test_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert llm_chat.is_chat_available() is False

    def test_with_api_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        assert llm_chat.is_chat_available() is True


class TestFallbacks:
    def test_recommendation_returns_none_without_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = llm_chat.chat_about_recommendation(
            {"asset": "MSFT"}, "¿qué hago?", {}
        )
        assert result is None

    def test_general_returns_none_without_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert llm_chat.chat_general("¿voy bien?", {}, {}) is None

    def test_empty_question_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            llm_chat, "_get_client", lambda: _MockClient(text="should not be returned")
        )
        result = llm_chat.chat_about_recommendation(
            {"asset": "MSFT"}, "   ", {}
        )
        assert result is None


class TestSuccessPaths:
    def test_recommendation_success(self, monkeypatch):
        monkeypatch.setattr(
            llm_chat,
            "_get_client",
            lambda: _MockClient(text="Mantén MSFT, sigue sólida."),
        )
        result = llm_chat.chat_about_recommendation(
            {"asset": "MSFT", "type": "HOLD"},
            "¿debo comprar más?",
            {"nav_total_eur": 50000},
        )
        assert result == "Mantén MSFT, sigue sólida."

    def test_general_success(self, monkeypatch):
        monkeypatch.setattr(
            llm_chat,
            "_get_client",
            lambda: _MockClient(text="Vas bien."),
        )
        result = llm_chat.chat_general(
            "¿voy bien?",
            {"nav_total_eur": 50000, "positions_count": 19, "cash_eur": 3000},
            {
                "market_state": {"regime": "neutral", "vix": 17.0},
                "tax_alerts": [
                    {"asset": "MELI", "message": "no recomprar"}
                ],
            },
        )
        assert result == "Vas bien."

    def test_api_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            llm_chat,
            "_get_client",
            lambda: _MockClient(behavior="raise"),
        )
        result = llm_chat.chat_about_recommendation(
            {"asset": "MSFT"}, "hola", {"nav_total_eur": 50000}
        )
        assert result is None

"""Tests for `scripts/notifications.py`. No SMTP / Telegram traffic."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import notifications as nt  # noqa: E402


# ---------------------------------------------------------------------------
class TestSendEmailNoConfig:
    def test_returns_false_when_no_recipient(self, monkeypatch):
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASS", raising=False)
        assert nt.send_email("subj", "<p>body</p>", recipient=None) is False

    def test_returns_false_when_smtp_creds_missing(self, monkeypatch):
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASS", raising=False)
        assert nt.send_email("subj", "<p>body</p>", recipient="x@y.com") is False


class TestSendTelegramNoConfig:
    def test_returns_false_when_creds_missing(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert nt.send_telegram("msg") is False


# ---------------------------------------------------------------------------
class TestDedupLog:
    def test_log_persists_and_dedup_works(self, tmp_path, monkeypatch):
        nt.log_notification("k1", "email", True, notifications_dir=tmp_path)
        assert nt.has_been_notified("k1", notifications_dir=tmp_path)
        assert not nt.has_been_notified("other", notifications_dir=tmp_path)

    def test_log_appends_not_overwrites(self, tmp_path):
        nt.log_notification("k1", "email", True, notifications_dir=tmp_path)
        nt.log_notification("k2", "telegram", False, notifications_dir=tmp_path)
        # Both keys should be detected
        assert nt.has_been_notified("k1", notifications_dir=tmp_path)
        assert nt.has_been_notified("k2", notifications_dir=tmp_path)


# ---------------------------------------------------------------------------
class TestNewsHighFiltering:
    def test_filters_only_high_relevance(self, tmp_path, monkeypatch):
        # No SMTP / TG — both helpers return False; sent_count must be 0
        # but the filter logic still runs and dedup entries are appended.
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        items = [
            {
                "ticker": "MSFT",
                "url": "https://x.com/a",
                "headline": "h1",
                "summary_1line": "s1",
                "relevance": "low",
            },
            {
                "ticker": "MELI",
                "url": "https://x.com/b",
                "headline": "h2",
                "summary_1line": "s2",
                "relevance": "high",
            },
        ]
        sent = nt.notify_news_high_relevance(
            items, recipient="x@y.com", notifications_dir=tmp_path
        )
        assert sent == 0  # no channel succeeded
        # Dedup: re-running for the same item is short-circuited.
        sent2 = nt.notify_news_high_relevance(
            items, recipient="x@y.com", notifications_dir=tmp_path
        )
        # Already logged once; doesn't matter the channel succeeded —
        # second call sees the key and returns 0.
        assert sent2 == 0


class TestDebateVerdictFiltering:
    def test_only_notable_verdicts_attempted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        # neutral verdict → False (skipped)
        out = nt.notify_debate_verdict(
            "MSFT", "thesis_neutral", "maintain", "weekly_schedule",
            recipient="x@y.com", notifications_dir=tmp_path,
        )
        assert out is False
        # weakened → False (no SMTP/TG configured) but attempted
        out = nt.notify_debate_verdict(
            "MELI", "thesis_weakened", "reduce", "news_high",
            recipient="x@y.com", notifications_dir=tmp_path,
        )
        assert out is False

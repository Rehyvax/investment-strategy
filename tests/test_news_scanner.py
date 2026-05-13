"""Tests for `scripts/news_scanner.py`.

Network calls (Yahoo / Google / FinnHub) and LLM calls are mocked or
exercised through the no-LLM fallback path. None of these tests issue
HTTP requests or burn API tokens.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import news_scanner as ns  # noqa: E402


# ---------------------------------------------------------------------------
# canonicalize_url
# ---------------------------------------------------------------------------
class TestCanonicalizeUrl:
    def test_strips_query_and_fragment(self):
        url = "https://example.com/article?utm_source=foo&id=1#x"
        assert ns.canonicalize_url(url) == "https://example.com/article"

    def test_preserves_path(self):
        url = "https://example.com/news/2026/05/14/title"
        assert ns.canonicalize_url(url) == url

    def test_handles_empty(self):
        assert ns.canonicalize_url("") == ""


# ---------------------------------------------------------------------------
# dedupe_news
# ---------------------------------------------------------------------------
class TestDedupe:
    def test_dedupe_by_canonical_url(self):
        items = [
            {"url": "https://x.com/a?utm_source=f", "headline": "first"},
            {"url": "https://x.com/a?ref=g", "headline": "duplicate"},
            {"url": "https://x.com/b", "headline": "third"},
        ]
        out = ns.dedupe_news(items)
        # First two collapse to the same canonical URL → one survivor.
        assert len(out) == 2
        assert out[0]["headline"] == "first"
        assert out[1]["headline"] == "third"

    def test_dedupe_by_headline_when_url_missing(self):
        items = [
            {"url": "", "headline": "AAPL beats earnings"},
            {"url": "", "headline": "AAPL beats earnings"},  # exact dup
            {"url": "", "headline": "Different headline"},
        ]
        out = ns.dedupe_news(items)
        assert len(out) == 2


# ---------------------------------------------------------------------------
# score_news_item — no-LLM fallback path
# ---------------------------------------------------------------------------
class TestScoring:
    def test_fallback_when_no_client(self, monkeypatch):
        # Force `_get_client` to return None so we exercise the fallback.
        monkeypatch.setattr(ns, "_get_client", lambda: None)
        item = {"ticker": "MSFT", "headline": "Microsoft launches X", "snippet": "..."}
        scored = ns.score_news_item(item)
        assert scored["relevance"] == "medium"
        assert scored["category"] == "other"
        assert scored["_scoring_source"] == "fallback_no_client"
        assert scored["summary_1line"].startswith("Microsoft launches X")

    def test_idempotent_when_already_scored(self, monkeypatch):
        # If `_get_client` were called we'd see a sentinel; ensure it isn't.
        called: list[bool] = []
        monkeypatch.setattr(
            ns, "_get_client", lambda: called.append(True) or None
        )
        item = {"ticker": "X", "relevance": "high", "category": "earnings"}
        out = ns.score_news_item(item)
        assert out is item
        assert not called  # short-circuited before the client lookup


# ---------------------------------------------------------------------------
# get_recent_news_for_asset — relevance + lookback filter
# ---------------------------------------------------------------------------
class TestRecentNewsReader:
    def _seed(self, tmp_path: Path, items: list[dict]) -> None:
        d = tmp_path / "news"
        d.mkdir(parents=True, exist_ok=True)
        month = date.today().strftime("%Y-%m")
        f = d / f"{month}.jsonl"
        with f.open("w", encoding="utf-8") as fp:
            for it in items:
                fp.write(json.dumps(it) + "\n")

    def test_filters_by_relevance(self, tmp_path, monkeypatch):
        self._seed(
            tmp_path,
            [
                {
                    "ticker": "AAPL",
                    "headline": "high item",
                    "relevance": "high",
                    "timestamp": "2026-05-14T10:00:00Z",
                },
                {
                    "ticker": "AAPL",
                    "headline": "low item",
                    "relevance": "low",
                    "timestamp": "2026-05-14T11:00:00Z",
                },
                {
                    "ticker": "MSFT",
                    "headline": "other ticker",
                    "relevance": "high",
                    "timestamp": "2026-05-14T12:00:00Z",
                },
            ],
        )
        monkeypatch.setattr(ns, "NEWS_DIR", tmp_path / "news")
        out = ns.get_recent_news_for_asset(
            "AAPL", lookback_days=30, min_relevance="medium"
        )
        # Low gets filtered out; only the high-relevance AAPL item remains.
        assert len(out) == 1
        assert out[0]["headline"] == "high item"


# ---------------------------------------------------------------------------
# discover_tickers_for_news
# ---------------------------------------------------------------------------
class TestDiscoverTickers:
    def test_returns_set_with_real_portfolio_tickers(self):
        out = ns.discover_tickers_for_news()
        assert isinstance(out, set)
        # Real portfolio (post-rotation 2026-05-14) holds 19 tickers
        # including MSFT and MELI; weaker assertion on either of them.
        assert "MSFT" in out or "MELI" in out

"""News scanner — multi-source ticker news aggregation + LLM relevance scoring.

Scope (Fase 3A):
- Discovers active tickers from real + factor-portfolio snapshots.
- Fetches headlines from Yahoo Finance RSS, Google News RSS, and FinnHub
  (when FINNHUB_API_KEY is set).
- Deduplicates by canonicalized URL + headline-hash fallback.
- Scores each new item via Claude Sonnet (relevance + category +
  one-line summary). Falls back to "medium" / "other" / first 100 chars
  of the headline when the LLM is not available, so the pipeline never
  hard-fails on missing API key.
- Persists materially-relevant items (medium + high) to monthly JSONL
  under data/events/news/{YYYY-MM}.jsonl.
- Provides `get_recent_news_for_asset()` for the cerebro generator.

Operational guarantees:
- Skips weekends (saturday + sunday) — no business news worth scoring.
- Atomic append (writes to .tmp then os.replace).
- Idempotent — already-stored URLs are filtered before fetch.
- Conservative timeouts (10s per HTTP) and silent per-source failures.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import feedparser
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

# Lazy import — keeps the module importable even when llm_narratives is
# unavailable (e.g. tests with no anthropic SDK installed).
try:
    from llm_narratives import MODEL, _get_client, is_llm_available  # type: ignore
except ImportError:  # pragma: no cover — defensive

    def is_llm_available() -> bool:  # type: ignore[no-redef]
        return False

    def _get_client():  # type: ignore[no-redef]
        return None

    MODEL = "claude-sonnet-4-6"  # type: ignore[assignment]


LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

NEWS_DIR = ROOT / "data" / "events" / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)

NEWS_LOOKBACK_DAYS = 7
MAX_NEWS_PER_SOURCE = 10
HTTP_TIMEOUT_SEC = 10

PORTFOLIO_DIRS = (
    "real",
    "shadow",
    "quality",
    "value",
    "momentum",
    "aggressive",
    "conservative",
)


# ---------------------------------------------------------------------------
# Logger — module-level configure happens only when run as a script
# ---------------------------------------------------------------------------
logger = logging.getLogger("news_scanner")


def _configure_logger() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOGS_DIR / "news_scanner.log", encoding="utf-8")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def fetch_yahoo_news(ticker: str) -> list[dict[str, Any]]:
    url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?"
        f"s={ticker}&region=US&lang=en-US"
    )
    items: list[dict[str, Any]] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:MAX_NEWS_PER_SOURCE]:
            items.append(
                {
                    "ticker": ticker,
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "timestamp": entry.get("published", ""),
                    "source": "yahoo_finance",
                    "snippet": (entry.get("summary", "") or "")[:500],
                }
            )
    except Exception as exc:  # noqa: BLE001 — surface but never fatal
        logger.warning(f"Yahoo RSS fetch failed for {ticker}: {exc}")
    return items


def fetch_google_news(ticker: str) -> list[dict[str, Any]]:
    # `quote` is required: feedparser cannot parse a URL with raw spaces,
    # which is what `f"{ticker} stock"` produces. `safe=""` forces all
    # non-alphanum characters (including space) to percent-encode.
    query = quote(f"{ticker} stock", safe="")
    url = (
        f"https://news.google.com/rss/search?q={query}"
        "&hl=en-US&gl=US&ceid=US:en"
    )
    items: list[dict[str, Any]] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:MAX_NEWS_PER_SOURCE]:
            items.append(
                {
                    "ticker": ticker,
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "timestamp": entry.get("published", ""),
                    "source": "google_news",
                    "snippet": (entry.get("summary", "") or "")[:500],
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Google News fetch failed for {ticker}: {exc}")
    return items


def fetch_finnhub_news(ticker: str) -> list[dict[str, Any]]:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return []
    today = date.today()
    from_date = (today - timedelta(days=NEWS_LOOKBACK_DAYS)).isoformat()
    to_date = today.isoformat()
    items: list[dict[str, Any]] = []
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": ticker,
                "from": from_date,
                "to": to_date,
                "token": api_key,
            },
            timeout=HTTP_TIMEOUT_SEC,
        )
        if resp.status_code == 200:
            for entry in resp.json()[:MAX_NEWS_PER_SOURCE]:
                ts = entry.get("datetime") or 0
                items.append(
                    {
                        "ticker": ticker,
                        "headline": entry.get("headline", ""),
                        "url": entry.get("url", ""),
                        "timestamp": (
                            datetime.fromtimestamp(ts, tz=timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z")
                        ),
                        "source": "finnhub",
                        "snippet": (entry.get("summary", "") or "")[:500],
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"FinnHub fetch failed for {ticker}: {exc}")
    return items


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
def canonicalize_url(url: str) -> str:
    """Strip query + fragment so trackers (utm_*, fbclid, ...) collapse to
    the same key. Empty / malformed input is returned as-is."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
        )
    except Exception:  # noqa: BLE001
        return url


def _headline_key(headline: str) -> str:
    norm = (headline or "").strip().lower()
    return hashlib.md5(norm.encode("utf-8")).hexdigest()  # noqa: S324 — dedup, not security


def dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url_key = canonicalize_url(item.get("url", ""))
        key = url_key if url_key else _headline_key(item.get("headline", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# LLM scoring
# ---------------------------------------------------------------------------
SCORING_PROMPT = """You are a financial news triage expert.

Stock ticker: {ticker}
Headline: {headline}
Snippet: {snippet}

Classify on two dimensions:

1. RELEVANCE (how materially does this affect {ticker}'s investment thesis?):
   high   = directly affects valuation / fundamentals (earnings, guidance,
            M&A, regulatory action, leadership change, major contract)
   medium = relevant context (sector trends, competitor moves, macro
            shifts affecting the stock)
   low    = tangential mention, generic market commentary, listicles

2. CATEGORY (pick one):
   earnings | regulatory | corporate_action | sentiment | macro |
   operational | other

Respond with a single-line JSON object only, no markdown fence:
{{"relevance":"high|medium|low","category":"...","summary_1line":"8-15 word summary"}}"""


def score_news_item(item: dict[str, Any]) -> dict[str, Any]:
    """Add `relevance`, `category`, `summary_1line`. Idempotent: if the
    item was already scored, returns it unchanged."""
    if item.get("relevance") and item.get("category"):
        return item

    client = _get_client()
    if client is None:
        item["relevance"] = "medium"
        item["category"] = "other"
        item["summary_1line"] = (item.get("headline") or "")[:100]
        item["_scoring_source"] = "fallback_no_client"
        return item

    try:
        prompt = SCORING_PROMPT.format(
            ticker=item.get("ticker", ""),
            headline=item.get("headline", ""),
            snippet=(item.get("snippet") or "")[:300],
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (response.content[0].text or "").strip()
        # Defensive: strip any accidental markdown fence the LLM may add.
        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        parsed = json.loads(text)
        item["relevance"] = parsed.get("relevance", "low")
        item["category"] = parsed.get("category", "other")
        item["summary_1line"] = parsed.get("summary_1line", "")
        item["_scoring_source"] = "llm"
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"LLM scoring failed for {item.get('ticker')}: {exc}")
        item["relevance"] = "medium"
        item["category"] = "other"
        item["summary_1line"] = (item.get("headline") or "")[:100]
        item["_scoring_source"] = "fallback_after_error"
    return item


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def get_existing_news_keys(month_str: str) -> set[str]:
    file_path = NEWS_DIR / f"{month_str}.jsonl"
    if not file_path.exists():
        return set()
    keys: set[str] = set()
    with file_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            url_key = canonicalize_url(item.get("url", ""))
            keys.add(
                url_key if url_key else _headline_key(item.get("headline", ""))
            )
    return keys


def append_news_items(items: list[dict[str, Any]], month_str: str) -> None:
    """Atomic append: read existing, build the new content in a tmp file,
    then `os.replace` it onto the destination."""
    file_path = NEWS_DIR / f"{month_str}.jsonl"
    tmp_path = file_path.with_suffix(".jsonl.tmp")
    existing = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    new_lines: list[str] = []
    for item in items:
        item.setdefault("ingested_at", now_iso)
        new_lines.append(json.dumps(item, ensure_ascii=False))
    body = existing + "\n".join(new_lines)
    if new_lines:
        body += "\n"
    tmp_path.write_text(body, encoding="utf-8")
    tmp_path.replace(file_path)


# ---------------------------------------------------------------------------
# Reader (cerebro consumer)
# ---------------------------------------------------------------------------
def get_recent_news_for_asset(
    ticker: str,
    lookback_days: int = 7,
    min_relevance: str = "medium",
    max_items: int = 5,
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Returns at most `max_items` news items for `ticker` in the trailing
    `lookback_days` window, filtered by relevance >= `min_relevance`."""
    relevance_order = {"low": 0, "medium": 1, "high": 2}
    min_score = relevance_order.get(min_relevance, 0)
    as_of = as_of or date.today()
    cutoff_dt = datetime(
        as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc
    ) - timedelta(days=lookback_days)

    months: list[str] = [as_of.strftime("%Y-%m")]
    if as_of.day < 8:
        prev = (as_of.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        months.append(prev)

    items: list[dict[str, Any]] = []
    for month_str in months:
        file_path = NEWS_DIR / f"{month_str}.jsonl"
        if not file_path.exists():
            continue
        with file_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("ticker") != ticker:
                    continue
                if (
                    relevance_order.get(item.get("relevance", "low"), 0)
                    < min_score
                ):
                    continue
                items.append(item)

    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items[:max_items]


# ---------------------------------------------------------------------------
# Ticker discovery
# ---------------------------------------------------------------------------
def discover_tickers_for_news() -> set[str]:
    """Union of tickers across the latest snapshot of every active
    portfolio (real + factor portfolios). Used by the daily runner."""
    tickers: set[str] = set()
    snaps_dir = ROOT / "data" / "snapshots"
    for portfolio_id in PORTFOLIO_DIRS:
        pdir = snaps_dir / portfolio_id
        if not pdir.exists():
            continue
        candidates: list[Path] = []
        for f in pdir.glob("*.json"):
            if f.name.startswith("_"):
                continue
            stem = f.stem
            if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                candidates.append(f)
        if not candidates:
            continue
        candidates.sort()
        try:
            data = json.loads(candidates[-1].read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for pos in data.get("positions", []) or []:
            t = pos.get("ticker")
            if isinstance(t, str) and t:
                tickers.add(t)
    return tickers


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    _configure_logger()
    import argparse

    p = argparse.ArgumentParser(description="News scanner daily runner.")
    p.add_argument(
        "--max-tickers",
        type=int,
        default=None,
        help="Cap number of tickers (debug / cost control).",
    )
    p.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM scoring; tag every item as medium/other.",
    )
    p.add_argument(
        "--force-weekend",
        action="store_true",
        help="Run even on Sat/Sun (otherwise skipped).",
    )
    args = p.parse_args(argv)

    logger.info("=" * 60)
    logger.info("News Scanner starting")

    today = date.today()
    if today.weekday() >= 5 and not args.force_weekend:
        logger.info(f"Weekend ({today.isoformat()}) — skipping news fetch")
        return 0

    tickers = sorted(discover_tickers_for_news())
    if args.max_tickers is not None:
        tickers = tickers[: args.max_tickers]
    logger.info(f"Discovered {len(tickers)} tickers: {tickers}")
    if not tickers:
        logger.warning("No tickers discovered, exiting cleanly")
        return 0

    month_str = today.strftime("%Y-%m")
    existing_keys = get_existing_news_keys(month_str)
    logger.info(f"Existing items in {month_str}.jsonl: {len(existing_keys)}")

    all_relevant: list[dict[str, Any]] = []
    fetched_total = 0
    for ticker in tickers:
        items = (
            fetch_yahoo_news(ticker)
            + fetch_google_news(ticker)
            + fetch_finnhub_news(ticker)
        )
        items = dedupe_news(items)
        items = [
            it
            for it in items
            if (canonicalize_url(it.get("url", "")) or _headline_key(it.get("headline", "")))
            not in existing_keys
        ]
        fetched_total += len(items)
        if args.no_llm:
            for it in items:
                it.setdefault("relevance", "medium")
                it.setdefault("category", "other")
                it.setdefault("summary_1line", (it.get("headline") or "")[:100])
                it["_scoring_source"] = "no_llm_flag"
        else:
            for it in items:
                score_news_item(it)
        relevant = [
            it for it in items if it.get("relevance") in ("medium", "high")
        ]
        logger.info(
            f"  {ticker}: fetched={len(items)} relevant_kept={len(relevant)}"
        )
        all_relevant.extend(relevant)
        # Update existing_keys so duplicates within the same run aren't
        # written twice.
        for it in items:
            url_key = canonicalize_url(it.get("url", "")) or _headline_key(
                it.get("headline", "")
            )
            existing_keys.add(url_key)

    if all_relevant:
        append_news_items(all_relevant, month_str)
        logger.info(
            f"Appended {len(all_relevant)} relevant items to {month_str}.jsonl"
        )

    high = sum(1 for it in all_relevant if it.get("relevance") == "high")
    medium = sum(1 for it in all_relevant if it.get("relevance") == "medium")
    logger.info(
        f"Summary: {fetched_total} fetched, {len(all_relevant)} kept "
        f"({high} high, {medium} medium)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Notifications dispatcher (email SMTP + Telegram bot, both optional).

Triggered by the cerebro generator after every regen. Never raises:
when SMTP / Telegram aren't configured the helpers return False and
the caller carries on.

Public surface:
    send_email(subject, body_html, recipient)            -> bool
    send_telegram(message)                                -> bool
    has_been_notified(key)                                -> bool
    log_notification(key, channel, success, *, dir=None)  -> None
    notify_news_high_relevance(news_items, recipient)     -> int  (count sent)
    notify_debate_verdict(ticker, verdict, action,
                          trigger_reason, recipient)      -> bool
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import sys
from datetime import date, datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NOTIFICATIONS_DIR = ROOT / "data" / "events" / "notifications"
NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Notable verdicts that warrant an email; quiet on neutral / strengthened.
NOTABLE_VERDICTS = {"thesis_weakened", "thesis_invalidated"}


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
def send_email(subject: str, body_html: str, recipient: str | None) -> bool:
    """SMTP send. Returns True on success, False on any failure (including
    missing config) — never raises."""
    if not recipient:
        return False
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    if not smtp_user or not smtp_pass:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [recipient], msg.as_string())
        logger.info(f"Email sent: {subject}")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"SMTP send failed: {exc}")
        return False


def send_telegram(message: str) -> bool:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    try:
        import requests
    except ImportError:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        ok = resp.status_code == 200
        if not ok:
            logger.warning(
                f"Telegram send failed: HTTP {resp.status_code}"
            )
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Telegram send error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Dedup log
# ---------------------------------------------------------------------------
def _log_path(*, notifications_dir: Path | None = None) -> Path:
    base = notifications_dir or NOTIFICATIONS_DIR
    base.mkdir(parents=True, exist_ok=True)
    today = date.today()
    return base / f"{today.strftime('%Y-%m')}.jsonl"


def has_been_notified(
    notification_key: str, *, notifications_dir: Path | None = None
) -> bool:
    f = _log_path(notifications_dir=notifications_dir)
    if not f.exists():
        return False
    try:
        with f.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("key") == notification_key:
                    return True
    except OSError:
        pass
    return False


def log_notification(
    notification_key: str,
    channel: str,
    success: bool,
    *,
    notifications_dir: Path | None = None,
) -> None:
    f = _log_path(notifications_dir=notifications_dir)
    entry = {
        "key": notification_key,
        "timestamp": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "channel": channel,
        "success": success,
    }
    with f.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Notification: news high relevance
# ---------------------------------------------------------------------------
def _build_news_email_html(item: dict[str, Any]) -> str:
    headline = item.get("headline") or ""
    summary = item.get("summary_1line") or ""
    snippet = (item.get("snippet") or "")[:300]
    url = item.get("url") or "#"
    ticker = item.get("ticker") or item.get("asset") or "?"
    category = item.get("category") or "other"
    source = item.get("source") or "unknown"
    ts = item.get("timestamp") or ""
    return (
        "<html><body style=\"font-family: Arial, sans-serif; "
        "max-width: 600px; margin: 0 auto;\">"
        f"<h2 style=\"color: #0F172A;\">News HIGH · {ticker}</h2>"
        f"<p style=\"color: #475569; font-size: 14px;\">"
        f"<strong>Category:</strong> {category}<br>"
        f"<strong>Source:</strong> {source}<br>"
        f"<strong>Time:</strong> {ts}</p>"
        "<div style=\"background: #FEF3C7; padding: 16px; "
        "border-left: 4px solid #D97706; margin: 16px 0;\">"
        f"<h3 style=\"margin: 0 0 8px 0; color: #92400E;\">{headline}</h3>"
        f"<p style=\"margin: 0; color: #451A03;\">{summary}</p></div>"
        f"<p style=\"font-size: 13px; color: #64748B;\">{snippet}…</p>"
        f"<p><a href=\"{url}\" style=\"color: #1E40AF;\">"
        "Leer artículo completo</a></p>"
        "<hr style=\"border: none; border-top: 1px solid #E2E8F0;\">"
        "<p style=\"font-size: 12px; color: #94A3B8;\">"
        "Esta noticia puede disparar un debate Bull/Bear si pulsas "
        "el barrido manual desde el sidebar del dashboard.</p>"
        "</body></html>"
    )


def notify_news_high_relevance(
    news_items: list[dict[str, Any]],
    recipient: str | None = None,
    *,
    notifications_dir: Path | None = None,
) -> int:
    """Returns number of items effectively notified (email or Telegram).
    Items already seen in the dedup log are skipped silently."""
    if not news_items:
        return 0
    recipient = recipient or os.environ.get("NOTIFY_EMAIL")
    sent = 0
    for item in news_items:
        if (item.get("relevance") or "").lower() != "high":
            continue
        ticker = item.get("ticker") or item.get("asset") or "?"
        url = item.get("url") or ""
        key = f"news_high:{ticker}:{url[:100]}"
        if has_been_notified(key, notifications_dir=notifications_dir):
            continue
        subject = (
            f"[Investment-AI] News HIGH {ticker}: "
            f"{(item.get('summary_1line') or item.get('headline') or '')[:80]}"
        )
        body = _build_news_email_html(item)
        email_ok = send_email(subject, body, recipient)
        log_notification(
            key, "email", email_ok, notifications_dir=notifications_dir
        )
        tg_msg = (
            f"<b>News HIGH {ticker}</b>\n"
            f"{item.get('headline', '')}\n\n"
            f"{item.get('summary_1line', '')}\n\n"
            f"<a href='{url}'>Leer</a>"
        )
        tg_ok = send_telegram(tg_msg)
        log_notification(
            key, "telegram", tg_ok, notifications_dir=notifications_dir
        )
        if email_ok or tg_ok:
            sent += 1
    return sent


# ---------------------------------------------------------------------------
# Notification: debate verdict
# ---------------------------------------------------------------------------
def notify_debate_verdict(
    ticker: str,
    verdict: str,
    suggested_action: str,
    trigger_reason: str,
    recipient: str | None = None,
    *,
    notifications_dir: Path | None = None,
) -> bool:
    """Only notable verdicts (`thesis_weakened`, `thesis_invalidated`)
    trigger an email. Returns True when at least one channel succeeded."""
    if verdict not in NOTABLE_VERDICTS:
        return False
    recipient = recipient or os.environ.get("NOTIFY_EMAIL")
    today = date.today().isoformat()
    key = f"debate:{ticker}:{verdict}:{today}"
    if has_been_notified(key, notifications_dir=notifications_dir):
        return False
    subject = f"[Investment-AI] Debate {verdict.upper()}: {ticker}"
    body = (
        "<html><body style=\"font-family: Arial, sans-serif;\">"
        f"<h2>Debate Bull/Bear · {ticker}</h2>"
        f"<p><strong>Verdict:</strong> {verdict}</p>"
        f"<p><strong>Suggested action:</strong> {suggested_action}</p>"
        f"<p><strong>Trigger:</strong> {trigger_reason}</p>"
        "<p>Revisa Pantalla 3 → Bloque H para transcripción completa.</p>"
        "</body></html>"
    )
    email_ok = send_email(subject, body, recipient)
    log_notification(
        key, "email", email_ok, notifications_dir=notifications_dir
    )
    tg_ok = send_telegram(
        f"<b>Debate {verdict.upper()} · {ticker}</b>\n"
        f"Action: {suggested_action}\n"
        f"Trigger: {trigger_reason}"
    )
    log_notification(
        key, "telegram", tg_ok, notifications_dir=notifications_dir
    )
    return email_ok or tg_ok


# ---------------------------------------------------------------------------
# Manual entry point — used by tests and the cerebro hook
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    cerebro_path = ROOT / "dashboard" / "data" / "cerebro_state.json"
    if not cerebro_path.exists():
        logger.error("cerebro_state.json not found")
        return 1
    state = json.loads(cerebro_path.read_text(encoding="utf-8"))
    sent_news = notify_news_high_relevance(state.get("news_feed") or [])
    logger.info(f"News notifications sent: {sent_news}")
    debates = state.get("debates_by_asset") or {}
    today_iso = date.today().isoformat()
    for ticker, debate in debates.items():
        if not isinstance(debate, dict):
            continue
        ts = debate.get("timestamp", "")
        if not ts.startswith(today_iso):
            continue
        notify_debate_verdict(
            ticker,
            debate.get("verdict", "thesis_neutral"),
            debate.get("suggested_action", "—"),
            debate.get("trigger_reason", "unknown"),
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

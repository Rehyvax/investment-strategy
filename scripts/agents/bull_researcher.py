"""Bull Researcher agent — steelmans the bullish thesis.

Invoked by the LangGraph debate orchestrator. Receives the assembled
`ticker_data` dict (thesis + technicals + fundamentals + news) and
produces an institutional-tone argument FOR maintaining or expanding
the position.

Public surface:
    bull_initial_argument(ticker_data) -> str | None
    bull_rebuttal(bear_argument, conversation_history) -> str | None

Returns None when no Anthropic client is configured; the graph falls
back to a placeholder argument so the debate flow doesn't hard-fail.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Borrow the project's shared Anthropic client + MODEL constant.
from llm_narratives import MODEL, get_client  # noqa: E402


BULL_SYSTEM_PROMPT = """You are a Bull Researcher in an institutional trading firm.
Your role is to STEELMAN the bullish thesis on a stock position using
available evidence.

Rules:
- Build the strongest possible case FOR continuing or expanding the position.
- Use SPECIFIC evidence from analyst reports (fundamentals, technicals,
  news, thesis) — cite data points (P/E, margins, growth rates,
  catalysts), no hand-waving.
- Acknowledge weaknesses but argue why they are manageable or temporary.
- Do NOT pretend everything is perfect — biased optimism is unhelpful.
- Do NOT use emojis, numeric confidence scores, or hedging like
  "could be" / "might be".
- Commit to the position: "The bull case rests on X, Y, Z."
- Tone: institutional, sober, evidence-driven.
- Max 6-8 sentences per round."""


BULL_INITIAL_PROMPT_TMPL = """Position: {ticker}
Position size: {weight_pct:.2f}% NAV (EUR {position_eur:,})
Current price: {current_price} {currency} | Cost basis: {cost_basis} {currency} | P&L {pnl_pct:+.2f}%

Thesis vigente: {thesis_summary}
Status: {thesis_status} | Verdict: {verdict}

Falsifier status:
{falsifiers_text}

Technical indicators:
- Trend: {trend}
- RSI(14): {rsi14} ({rsi_signal})
- MACD: {macd_signal}
- Bollinger: {bb_position}

Fundamentals:
- P/E: {pe_ratio} (forward {forward_pe})
- Operating margin: {operating_margin}
- Revenue growth: {revenue_growth}
- Debt/Equity: {debt_to_equity}
- Analyst target: {target_price} (consensus {recommendation})
- Red flags: {flags}

Recent material news ({n_news} items):
{news_text}

Build the BULL CASE for this position. 6-8 sentences. Use the evidence above."""


BULL_REBUTTAL_PROMPT_TMPL = """The Bear Researcher just argued:

\"\"\"
{bear_argument}
\"\"\"

Counter the bear case while acknowledging valid points. Use new evidence
or reframe existing evidence. Do not repeat your initial argument verbatim.
6-8 sentences max."""


# ---------------------------------------------------------------------------
# Helpers (shared with bear_researcher; duplicated locally to keep the
# package modular — neither agent imports from the other)
# ---------------------------------------------------------------------------
def _format_falsifiers(falsifiers: list[dict[str, Any]] | None) -> str:
    falsifiers = falsifiers or []
    lines: list[str] = []
    for f in falsifiers[:5]:
        status = f.get("status", "unknown")
        symbol = (
            "OK"
            if status == "inactive"
            else ("HALFWAY" if status == "halfway_activated" else "BREACH")
        )
        lines.append(f"  [{symbol}] {f.get('name', '?')}: {status}")
    return "\n".join(lines) if lines else "Sin falsifiers definidos"


def _format_news(news: list[dict[str, Any]] | None) -> str:
    news = news or []
    if not news:
        return "Sin noticias materiales recientes"
    lines: list[str] = []
    for n in news[:5]:
        relevance = (n.get("relevance") or "low").upper()
        summary = n.get("summary_1line") or (n.get("headline") or "")[:100]
        lines.append(f"  [{relevance}] {summary}")
    return "\n".join(lines)


def _build_initial_prompt(ticker_data: dict[str, Any], template: str) -> str:
    t = ticker_data.get("technicals") or {}
    f = ticker_data.get("fundamentals") or {}
    target_price = f.get("target_mean_price")
    target_str = (
        f"${target_price:.2f}" if isinstance(target_price, (int, float))
        else "N/A"
    )
    return template.format(
        ticker=ticker_data.get("ticker", "?"),
        weight_pct=float(ticker_data.get("weight_pct") or 0.0),
        position_eur=int(ticker_data.get("position_eur") or 0),
        current_price=ticker_data.get("current_price", "N/A"),
        cost_basis=ticker_data.get("cost_basis", "N/A"),
        pnl_pct=float(ticker_data.get("pnl_pct") or 0.0),
        currency=ticker_data.get("currency", "USD"),
        thesis_summary=(ticker_data.get("thesis_summary") or "—")[:400],
        thesis_status=ticker_data.get("thesis_status", "unknown"),
        verdict=ticker_data.get("verdict", "unknown"),
        falsifiers_text=_format_falsifiers(ticker_data.get("falsifiers")),
        trend=t.get("trend", "unknown"),
        rsi14=t.get("rsi14", "N/A"),
        rsi_signal=t.get("rsi_signal", "unknown"),
        macd_signal=t.get("macd_signal", "unknown"),
        bb_position=t.get("bb_position", "unknown"),
        pe_ratio=f.get("pe_ratio") or "N/A",
        forward_pe=f.get("forward_pe") or "N/A",
        operating_margin=f.get("operating_margin") or "N/A",
        revenue_growth=f.get("revenue_growth") or "N/A",
        debt_to_equity=f.get("debt_to_equity") or "N/A",
        target_price=target_str,
        recommendation=f.get("recommendation_key") or "N/A",
        flags=", ".join(f.get("flags") or []) or "ninguna",
        n_news=len(ticker_data.get("news") or []),
        news_text=_format_news(ticker_data.get("news")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def bull_initial_argument(ticker_data: dict[str, Any]) -> str | None:
    client = get_client()
    if client is None:
        return None
    prompt = _build_initial_prompt(ticker_data, BULL_INITIAL_PROMPT_TMPL)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=BULL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as exc:  # noqa: BLE001
        print(f"Bull initial error for {ticker_data.get('ticker')}: {exc}")
        return None


def bull_rebuttal(
    bear_argument: str, conversation_history: list[dict[str, str]] | None = None
) -> str | None:
    client = get_client()
    if client is None:
        return None
    history = list(conversation_history or [])
    user_msg = BULL_REBUTTAL_PROMPT_TMPL.format(bear_argument=bear_argument)
    messages = history + [{"role": "user", "content": user_msg}]
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=BULL_SYSTEM_PROMPT,
            messages=messages,
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as exc:  # noqa: BLE001
        print(f"Bull rebuttal error: {exc}")
        return None

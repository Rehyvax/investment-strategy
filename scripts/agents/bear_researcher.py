"""Bear Researcher agent — red-teams the bullish thesis.

Symmetric to bull_researcher: same input shape, opposite framing.
Returns None when no Anthropic client is configured.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from llm_narratives import MODEL, get_client  # noqa: E402

# Reuse the same prompt-builder from bull_researcher to avoid drift.
from scripts.agents.bull_researcher import _build_initial_prompt  # noqa: E402


BEAR_SYSTEM_PROMPT = """You are a Bear Researcher in an institutional trading firm.
Your role is to RED-TEAM the bullish thesis on a stock position using
available evidence.

Rules:
- Build the strongest possible case AGAINST the position
  (sell, reduce, exit).
- Use SPECIFIC evidence from analyst reports — cite data points;
  no vague pessimism.
- Identify concrete invalidation conditions and risks.
- Acknowledge what's working but argue why downside dominates.
- Do NOT exaggerate or fearmonger — biased pessimism is also unhelpful.
- Do NOT use emojis, numeric confidence scores, or hedging.
- Commit: "The bear case rests on X, Y, Z."
- Tone: institutional, sober, evidence-driven, focused on what can go wrong.
- Max 6-8 sentences per round."""


BEAR_INITIAL_PROMPT_TMPL = """Position: {ticker}
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

Build the BEAR CASE against this position. 6-8 sentences. Use the evidence
above to identify concrete risks, invalidation triggers, and reasons to
exit or reduce."""


BEAR_REBUTTAL_PROMPT_TMPL = """The Bull Researcher just argued:

\"\"\"
{bull_argument}
\"\"\"

Counter the bull case. Identify where they overstate, what they ignore,
or how their evidence can be reinterpreted bearishly. Do not repeat your
initial argument verbatim. 6-8 sentences max."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def bear_initial_argument(ticker_data: dict[str, Any]) -> str | None:
    client = get_client()
    if client is None:
        return None
    prompt = _build_initial_prompt(ticker_data, BEAR_INITIAL_PROMPT_TMPL)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=BEAR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as exc:  # noqa: BLE001
        print(f"Bear initial error for {ticker_data.get('ticker')}: {exc}")
        return None


def bear_rebuttal(
    bull_argument: str, conversation_history: list[dict[str, str]] | None = None
) -> str | None:
    client = get_client()
    if client is None:
        return None
    history = list(conversation_history or [])
    user_msg = BEAR_REBUTTAL_PROMPT_TMPL.format(bull_argument=bull_argument)
    messages = history + [{"role": "user", "content": user_msg}]
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=BEAR_SYSTEM_PROMPT,
            messages=messages,
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as exc:  # noqa: BLE001
        print(f"Bear rebuttal error: {exc}")
        return None

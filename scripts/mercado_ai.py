"""Mercado-AI conversational chat (Pantalla 6).

Wraps Anthropic Sonnet with a portfolio context injection that keeps
each turn grounded in the user's actual snapshot + cerebro state:

    - KPIs (NAV, cash, n positions)
    - Top sector / country concentrations
    - All positions one-line each (capped at 25)
    - Active recommendations (top 5)
    - Recent debates (top 5 tickers)
    - Brier 30d signal

When the user mentions a ticker the prompt also receives an asset
detail block (news, technicals, fundamentals, last debate). The
ticker scan is alphabet-aware so substring matches don't fire (BAC
inside "back" is rejected).

Cost target: ~$0.02-0.05 per turn (Sonnet 4.6 with ~3-5k input tokens).
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from llm_narratives import MODEL, get_client  # noqa: E402

logger = logging.getLogger(__name__)

MAX_TOKENS_REPLY = 800
MAX_HISTORY_TURNS = 5  # caller stores user+assistant separately, so 10 messages
MAX_POSITIONS_IN_CONTEXT = 25
MAX_TICKERS_DETAIL = 5


MERCADO_AI_SYSTEM_PROMPT = """Eres un asesor financiero institucional sobrio
con acceso a un sistema multi-agente de análisis de cartera (snapshot real,
cerebro state, news, technicals, fundamentals, debates Bull/Bear).

Tu rol: responder preguntas del usuario sobre su cartera, mercado,
posiciones específicas, comparativas o estrategia, usando el contexto
provisto en cada turno.

Reglas estrictas:
- NO emojis, NO scores numéricos artificiales, NO menús de opciones
- COMPROMETETE con UNA respuesta directa
- Si la pregunta requiere datos que NO están en contexto, dilo
  explícitamente — no inventes precios, ratios ni eventos
- Cita tickers en mayúsculas (MSFT, no "Microsoft" en análisis técnico)
- Si el usuario pide una acción concreta (vender / comprar / aumentar),
  refiere al debate Bull vs Bear vigente o sugiere lanzar uno desde
  Pantalla 3 si no existe
- Para fiscal / LIRPF / 2-month rule, refiere a Pantalla 9
- Para tesis específica, refiere a Pantalla 3 ticker
- Tono institucional, no comercial
- Máximo 6-8 frases salvo pregunta multi-parte"""


# ---------------------------------------------------------------------------
# Pure context builders (testable without LLM)
# ---------------------------------------------------------------------------
def build_context_summary(
    cerebro_state: dict[str, Any], snapshot: dict[str, Any]
) -> str:
    nav = float(snapshot.get("nav_total_eur") or 0.0)
    cash = float(snapshot.get("cash_eur") or 0.0)
    positions = snapshot.get("positions") or []
    n_pos = len(positions)
    lines: list[str] = [
        f"Cartera: NAV €{int(nav):,}, cash €{int(cash):,}, {n_pos} posiciones"
    ]
    sectors: dict[str, float] = {}
    countries: dict[str, float] = {}
    for p in positions:
        weight = _weight(p, nav)
        sec = p.get("sector_at_purchase") or "Unknown"
        ctr = p.get("country_at_purchase") or "Unknown"
        sectors[sec] = sectors.get(sec, 0.0) + weight
        countries[ctr] = countries.get(ctr, 0.0) + weight
    top_sectors = sorted(sectors.items(), key=lambda x: -x[1])[:3]
    top_countries = sorted(countries.items(), key=lambda x: -x[1])[:2]
    if top_sectors:
        lines.append(
            "Top sectors: "
            + ", ".join(f"{s} {p:.0f}%" for s, p in top_sectors)
        )
    if top_countries:
        lines.append(
            "Top countries: "
            + ", ".join(f"{c} {p:.0f}%" for c, p in top_countries)
        )

    lines.append("\nPosiciones (ticker | weight% | P&L%):")
    for p in sorted(positions, key=lambda x: -_weight(x, nav))[
        :MAX_POSITIONS_IN_CONTEXT
    ]:
        cb = float(p.get("cost_basis_per_share_native") or 0.0)
        cur = float(p.get("current_price_native") or 0.0)
        pnl_pct = ((cur / cb - 1.0) * 100.0) if cb > 0 else 0.0
        weight = _weight(p, nav)
        lines.append(
            f"  {p.get('ticker', '?')} | {weight:.1f}% | {pnl_pct:+.1f}%"
        )

    recs = cerebro_state.get("recommendations") or []
    if recs:
        lines.append(f"\nRecommendations activas: {len(recs)}")
        for r in recs[:5]:
            lines.append(
                f"  {r.get('asset', '?')}: "
                f"{r.get('type') or r.get('action', '?')} "
                f"({r.get('priority', 'medium')})"
            )

    debates = cerebro_state.get("debates_by_asset") or {}
    if debates:
        lines.append(f"\nDebates recientes ({len(debates)} tickers):")
        for ticker, debate in list(debates.items())[:5]:
            if isinstance(debate, dict):
                lines.append(
                    f"  {ticker}: {debate.get('verdict', '?')} "
                    f"({(debate.get('timestamp') or '')[:10]})"
                )

    market = cerebro_state.get("market_state") or {}
    explanation = market.get("explanation") or market.get("regime")
    if explanation:
        lines.append(f"\nMercado actual: {str(explanation)[:400]}")

    brier = cerebro_state.get("brier_score_30d")
    n_eval = cerebro_state.get("brier_n_evaluations_30d") or 0
    if brier is not None:
        lines.append(f"\nBrier 30d: {brier:.3f} (n={n_eval})")
    return "\n".join(lines)


def build_asset_detail(cerebro_state: dict[str, Any], ticker: str) -> str:
    lines: list[str] = [f"Detalle {ticker}:"]
    news = (cerebro_state.get("news_by_asset") or {}).get(ticker) or []
    if news:
        lines.append(f"  News ({len(news)} recientes):")
        for n in news[:3]:
            relevance = (n.get("relevance") or "low").upper()
            summary = (
                n.get("summary_1line")
                or (n.get("headline") or "")[:100]
            )
            lines.append(f"    [{relevance}] {summary}")
    tech = (cerebro_state.get("technicals_by_asset") or {}).get(ticker) or {}
    if tech:
        lines.append(
            "  Technicals: "
            f"trend={tech.get('trend')}, "
            f"RSI={tech.get('rsi14')} ({tech.get('rsi_signal')}), "
            f"MACD={tech.get('macd_signal')}, "
            f"BB={tech.get('bb_position')}"
        )
    fund = (cerebro_state.get("fundamentals_by_asset") or {}).get(ticker) or {}
    if fund:
        target = fund.get("target_mean_price")
        target_str = f"${target:.2f}" if isinstance(target, (int, float)) else "N/A"
        lines.append(
            "  Fundamentals: "
            f"P/E={fund.get('pe_ratio')}, "
            f"OpMargin={fund.get('operating_margin')}, "
            f"RevGrowth={fund.get('revenue_growth')}, "
            f"Target={target_str} ({fund.get('recommendation_key')})"
        )
        flags = fund.get("flags") or []
        if flags:
            lines.append(f"    Red flags: {', '.join(flags)}")
    debate = (cerebro_state.get("debates_by_asset") or {}).get(ticker)
    if isinstance(debate, dict):
        lines.append(
            "  Último debate "
            f"({(debate.get('timestamp') or '')[:10]}): "
            f"{debate.get('verdict')}, "
            f"action={debate.get('suggested_action')}, "
            f"confianza={debate.get('confidence')}"
        )
    return "\n".join(lines)


# Word-boundary regex so "BAC" in "back" doesn't match. We use the
# pattern (?<![A-Z0-9])TICKER(?![A-Z0-9]) on the upper-cased message.
def extract_tickers_mentioned(
    user_message: str, known_tickers: list[str]
) -> list[str]:
    if not user_message or not known_tickers:
        return []
    msg = user_message.upper()
    found: list[str] = []
    for ticker in known_tickers:
        if not ticker:
            continue
        pattern = rf"(?<![A-Z0-9]){re.escape(ticker.upper())}(?![A-Z0-9])"
        if re.search(pattern, msg):
            found.append(ticker)
        if len(found) >= MAX_TICKERS_DETAIL:
            break
    return found


# ---------------------------------------------------------------------------
# Public chat entry
# ---------------------------------------------------------------------------
def chat_mercado_ai(
    user_message: str,
    conversation_history: list[dict[str, Any]] | None,
    cerebro_state: dict[str, Any],
    snapshot: dict[str, Any],
) -> str | None:
    client = get_client()
    if client is None:
        return None
    context_summary = build_context_summary(cerebro_state, snapshot)
    known_tickers = [
        p.get("ticker")
        for p in (snapshot.get("positions") or [])
        if isinstance(p.get("ticker"), str)
    ]
    mentioned = extract_tickers_mentioned(user_message, known_tickers)
    asset_details = "\n".join(
        build_asset_detail(cerebro_state, t) for t in mentioned
    )
    user_prompt_parts: list[str] = [
        f"CONTEXTO ACTUAL ({snapshot.get('as_of_date', 'hoy')}):",
        "",
        context_summary,
    ]
    if asset_details:
        user_prompt_parts.append("")
        user_prompt_parts.append(asset_details)
    user_prompt_parts.extend(["", "PREGUNTA:", user_message])
    user_prompt = "\n".join(user_prompt_parts)

    history = list(conversation_history or [])
    # Trim to last MAX_HISTORY_TURNS turns (each turn = 2 messages).
    if len(history) > MAX_HISTORY_TURNS * 2:
        history = history[-MAX_HISTORY_TURNS * 2 :]
    messages: list[dict[str, str]] = [
        {"role": h["role"], "content": h["content"]} for h in history
    ]
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_REPLY,
            system=MERCADO_AI_SYSTEM_PROMPT,
            messages=messages,
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Mercado-AI error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------
def _weight(position: dict[str, Any], nav: float) -> float:
    w = position.get("weight_pct")
    if isinstance(w, (int, float)) and w > 0:
        return float(w)
    cv = position.get("current_value_eur")
    if isinstance(cv, (int, float)) and nav > 0:
        return float(cv) / nav * 100.0
    return 0.0

"""Claude Autonomous paper trader (Fase 6 Parte E).

Daily decision routine that:
  1. Pulls Alpaca paper account state + open positions
  2. Reads cerebro context (news, market state, brier)
  3. Asks Sonnet for ONE of {hold | trade | rebalance} with structured JSON
  4. Persists the decision + self-critique to data/events/claude_autonomous_decisions/
  5. Executes any trades via Alpaca paper (TIF=DAY market orders)

The LLM call uses `call_llm_cached` so the system prompt + the universe
scanner output (both stable across the trading day) are eligible for the
prompt cache. Empty / no-op fallbacks when Alpaca or Anthropic missing.

Public:
    make_autonomous_decision(cerebro_state) -> dict | None
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
# Do NOT add ROOT/"scripts" — would shadow alpaca-py SDK. Use scripts.X
# fully qualified imports instead.
sys.path.insert(0, str(ROOT))

from scripts.llm_narratives import call_llm_cached  # noqa: E402
from scripts.alpaca.client import (  # noqa: E402
    alpaca_available,
    get_account_summary,
    get_positions,
    place_market_order,
)

logger = logging.getLogger(__name__)

DECISIONS_DIR = ROOT / "data" / "events" / "claude_autonomous_decisions"
DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"

INITIAL_EQUITY_USD = 50_000.0
MAX_TRADES_PER_DECISION = 5

AUTONOMOUS_SYSTEM_PROMPT = """Eres un gestor de cartera autónomo operando
un fondo paper-trading de $50,000 en Alpaca. Tu objetivo: batir al S&P 500
a 12 meses con rentabilidad ajustada al riesgo (Sharpe > 1).

Universo: cualquier US equity tradable en Alpaca (NYSE/NASDAQ/AMEX).
Sin restricciones de caps. Decides libremente: concentración, sector,
cash buffer, rebalancing, holding period.

Restricciones REALES:
- No usar margin (no leverage)
- No shorting (solo long-only)
- No options ni derivados
- Comisiones $0 (Alpaca paper)

Reglas estrictas:
1. Cada decisión explica UNA tesis clara con evidencia
2. NO emojis, NO opciones múltiples, COMPROMÉTETE con UNA acción
3. Si decides NO operar, justifica por qué hold supera trade
4. Mide tu progreso vs SPY y vs benchmarks
5. Aprende de tus errores pasados (revisa P&L realized por ticker)

Tono: institucional sobrio, sin tecno-optimismo ni catastrofismo.

OUTPUT FORMAT — JSON estricto en una línea seguida de auto-crítica:

{"decision_type":"hold|trade|rebalance","reasoning_overall":"...","trades":[{"ticker":"...","action":"buy|sell","qty":int,"thesis":"...","confidence":"high|medium|low","exit_trigger":"..."}],"rebalance_target":{"TICKER":pct},"expected_horizon_days":int,"self_assessed_risk":"low|medium|high"}

Luego en líneas separadas, una frase de auto-crítica:
"¿Qué podría estar equivocado en mi razonamiento?"

Si decision_type=hold → trades:[], rebalance_target:null
Si decision_type=trade → trades:[...], rebalance_target:null, máximo 5 trades
Si decision_type=rebalance → trades:[], rebalance_target:{...}"""


# ---------------------------------------------------------------------------
# Universe scanner
# ---------------------------------------------------------------------------
DEFAULT_UNIVERSE = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
    "UNH", "JPM", "JNJ", "V", "PG", "XOM", "MA", "HD", "CVX", "MRK",
    "LLY", "ABBV", "PEP", "AVGO", "KO", "COST", "TMO", "ORCL", "CRM",
    "ADBE", "NFLX", "AMD", "INTC", "QCOM", "IBM", "TXN", "NOW",
)


def get_universe_scanner_results(
    max_candidates: int = 10,
) -> list[dict[str, Any]]:
    """Light scan: random sample of large-caps with positive momentum +
    reasonable fundamentals. Always returns SOMETHING (even empty list)
    so the autonomous decision still gets context."""
    try:
        import yfinance as yf
    except ImportError:
        return []
    import random
    sample = random.sample(DEFAULT_UNIVERSE, min(20, len(DEFAULT_UNIVERSE)))
    candidates: list[dict[str, Any]] = []
    for ticker in sample:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:  # noqa: BLE001
            continue
        pe = info.get("trailingPE")
        rev_growth = info.get("revenueGrowth")
        if not isinstance(pe, (int, float)) or not isinstance(rev_growth, (int, float)):
            continue
        if pe <= 0 or pe > 100 or rev_growth < 0.05:
            continue
        candidates.append(
            {
                "ticker": ticker,
                "pe": round(float(pe), 2),
                "rev_growth": round(float(rev_growth), 4),
                "market_cap": info.get("marketCap"),
                "sector": info.get("sector"),
            }
        )
    candidates.sort(key=lambda x: x["pe"] / max(x["rev_growth"], 0.01))
    return candidates[:max_candidates]


# ---------------------------------------------------------------------------
# Performance lookups
# ---------------------------------------------------------------------------
def _portfolio_30d_return(portfolio_id: str) -> float:
    pdir = SNAPSHOTS_DIR / portfolio_id
    if not pdir.exists():
        return 0.0
    snaps: list[tuple[date, float]] = []
    cutoff = date.today() - timedelta(days=35)
    for f in pdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if not (len(stem) == 10 and stem[4] == "-" and stem[7] == "-"):
            continue
        try:
            d = date.fromisoformat(stem)
        except ValueError:
            continue
        if d < cutoff:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        nav = data.get("nav_total_eur") or data.get("equity") or 0.0
        try:
            nav = float(nav)
        except (TypeError, ValueError):
            continue
        if nav > 0:
            snaps.append((d, nav))
    if len(snaps) < 2:
        return 0.0
    snaps.sort(key=lambda x: x[0])
    return ((snaps[-1][1] - snaps[0][1]) / snaps[0][1]) * 100.0


def _recent_autonomous_reflections() -> str:
    """Last 3 reflection texts as bullet lines."""
    rdir = ROOT / "data" / "events" / "claude_autonomous_reflections"
    if not rdir.exists():
        return "  Sin reflexiones previas (sistema recién iniciado)"
    all_r: list[dict[str, Any]] = []
    for f in rdir.glob("*.jsonl"):
        try:
            with f.open("r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        all_r.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    if not all_r:
        return "  Sin reflexiones previas"
    all_r.sort(key=lambda x: x.get("reflection_timestamp") or x.get("ts", ""), reverse=True)
    lines: list[str] = []
    for r in all_r[:3]:
        ts = (r.get("reflection_timestamp") or r.get("ts", ""))[:10]
        outcome = r.get("outcome") or r.get("brier_correct", "?")
        lesson = (r.get("lesson") or r.get("reflection_text", ""))[:200]
        lines.append(f"  [{ts}] outcome={outcome}: {lesson}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt assembly + JSON parsing
# ---------------------------------------------------------------------------
def _build_user_prompt(
    *,
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    pnl_pct: float,
    claude_30d: float,
    spy_30d: float,
    lluis_30d: float,
    market_state: str,
    opportunities: list[dict[str, Any]],
    news_items: list[dict[str, Any]],
    brier_score: Any,
    reflections: str,
) -> str:
    positions_text = (
        "\n".join(
            f"  {p['ticker']}: {p['shares']:.2f} sh @ ${p['avg_entry_price']:.2f} avg, "
            f"now ${p['current_price']:.2f} (P&L {p['unrealized_plpc']:+.2f}%, "
            f"${p['unrealized_pl']:+.2f})"
            for p in positions
        )
        if positions
        else "  (Sin posiciones — todo en cash)"
    )
    opportunities_text = (
        "\n".join(
            f"  {o['ticker']}: PE {o.get('pe', 'N/A')}, RevGrowth "
            f"{(o.get('rev_growth') or 0) * 100:.1f}%, Sector: {o.get('sector', 'N/A')}"
            for o in opportunities
        )
        if opportunities
        else "  (Scanner sin candidatos hoy)"
    )
    news_text = (
        "\n".join(
            f"  [{n.get('ticker') or n.get('asset') or '?'}] "
            f"{n.get('summary_1line') or (n.get('headline') or '')[:100]}"
            for n in news_items[:5]
        )
        if news_items
        else "  Sin noticias high relevance"
    )
    brier_str = (
        f"{brier_score:.3f}" if isinstance(brier_score, (int, float))
        else "pending (n insuficiente)"
    )
    return f"""ESTADO DE TU CARTERA (inicial $50k):

Cash disponible: ${int(account['cash']):,}
Equity total: ${int(account['equity']):,}
P&L vs inicial: {pnl_pct:+.2f}%
Posiciones actuales ({len(positions)}):
{positions_text}

PERFORMANCE COMPARATIVA (últimos 30 días):
- Tu cartera (Claude): {claude_30d:+.2f}%
- SPY: {spy_30d:+.2f}%
- Lluis cartera real: {lluis_30d:+.2f}%

CONTEXTO MERCADO:
{market_state}

OPORTUNIDADES IDENTIFICADAS (scanner momentum/value):
{opportunities_text}

NEWS HIGH RELEVANCE últimas 24h:
{news_text}

REFLEXIÓN sobre decisiones pasadas (Brier score actual: {brier_str}):
{reflections}

DECISIÓN DE HOY:

Tienes 3 opciones (escoge SOLO una con razonamiento):
- HOLD: justifica por qué la cartera actual ya es óptima.
- TRADE: propone 1-{MAX_TRADES_PER_DECISION} trades concretos (ticker, action, qty, thesis, confidence, exit_trigger).
- REBALANCE: propone composición target en %.

Responde con la JSON estricta del system prompt seguida de la frase de auto-crítica."""


def _parse_decision_response(text: str) -> dict[str, Any] | None:
    """Best-effort JSON-line extraction. Picks the first balanced
    `{ ... }` block; the remainder becomes `self_critique`."""
    if not text:
        return None
    # Strip leading markdown fence if present.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    # Find first '{' and the matching '}'.
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    in_str = False
    escape = False
    for i, c in enumerate(cleaned[start:], start=start):
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    try:
        decision = json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        return None
    critique = cleaned[end:].strip()
    if critique:
        decision["self_critique"] = critique[:500]
    decision.setdefault("decision_type", "hold")
    decision.setdefault("trades", [])
    decision.setdefault("rebalance_target", None)
    decision.setdefault("expected_horizon_days", 0)
    decision.setdefault("self_assessed_risk", "medium")
    return decision


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def make_autonomous_decision(
    cerebro_state: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Run a full daily decision. `dry_run=True` skips Alpaca order
    submission (the LLM call still happens — useful for validating
    prompt quality without spending paper $)."""
    cerebro_state = cerebro_state or {}
    if not alpaca_available():
        logger.error("Alpaca client unavailable; skipping decision.")
        return None
    account = get_account_summary()
    if account is None:
        logger.error("Alpaca account unreachable.")
        return None
    positions = get_positions()
    pnl_pct = (
        ((account["equity"] - INITIAL_EQUITY_USD) / INITIAL_EQUITY_USD) * 100.0
    )
    claude_30d = _portfolio_30d_return("claude_autonomous")
    spy_30d = _portfolio_30d_return("spy_benchmark")
    lluis_30d = _portfolio_30d_return("real")

    market = cerebro_state.get("market_state") or {}
    market_state = (
        market.get("explanation") or market.get("regime") or "Sin lectura."
    )[:500]

    opportunities = get_universe_scanner_results(max_candidates=10)
    news_items = cerebro_state.get("news_feed") or []
    brier = cerebro_state.get("brier_score_30d")
    reflections = _recent_autonomous_reflections()

    user_prompt = _build_user_prompt(
        account=account,
        positions=positions,
        pnl_pct=pnl_pct,
        claude_30d=claude_30d,
        spy_30d=spy_30d,
        lluis_30d=lluis_30d,
        market_state=market_state,
        opportunities=opportunities,
        news_items=news_items,
        brier_score=brier,
        reflections=reflections,
    )

    response_text = call_llm_cached(
        system_prompt="",  # AUTONOMOUS_SYSTEM_PROMPT is the cacheable block
        user_prompt=user_prompt,
        cache_blocks=[AUTONOMOUS_SYSTEM_PROMPT],
        max_tokens=1500,
        caller="claude_autonomous",
    )
    if response_text is None:
        logger.error("LLM call failed for autonomous decision.")
        return None

    decision = _parse_decision_response(response_text)
    if decision is None:
        logger.error("Could not parse decision JSON; raw response stored.")
        decision = {
            "decision_type": "hold",
            "reasoning_overall": "Parse failure — defaulted to hold.",
            "trades": [],
            "rebalance_target": None,
            "self_critique": response_text[:500],
            "_parse_error": True,
        }

    decision["timestamp"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    decision["account_state_before"] = account
    decision["positions_before_count"] = len(positions)

    if decision["decision_type"] == "trade" and not dry_run:
        executed: list[dict[str, Any]] = []
        for trade in decision.get("trades", [])[:MAX_TRADES_PER_DECISION]:
            ticker = trade.get("ticker")
            qty = trade.get("qty")
            action = trade.get("action")
            thesis = trade.get("thesis", "")
            if not (
                isinstance(ticker, str) and isinstance(qty, (int, float))
                and isinstance(action, str) and qty > 0
            ):
                trade["_skip_reason"] = "invalid_fields"
                executed.append(trade)
                continue
            order = place_market_order(
                ticker=ticker,
                qty=float(qty),
                side=action.lower(),
                reasoning=thesis,
            )
            trade["order_result"] = order
            executed.append(trade)
        decision["trades"] = executed

    f = DECISIONS_DIR / f"{date.today().strftime('%Y-%m')}.jsonl"
    with f.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(decision, ensure_ascii=False) + "\n")
    return decision

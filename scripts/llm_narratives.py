"""Anthropic API integration for honest, committed narratives.

Phase 2B-2 of the dashboard pipeline. Wraps Claude Sonnet 4.6 (the
current Sonnet family member; the original session spec mentioned
"Sonnet 4.5" but the live model ID is `claude-sonnet-4-6`).

Design constraints reflected in every prompt:
- No emojis. No numeric confidence scores ("82% confianza").
- Committed opinion: a single direction, not a menu of options.
- Nuanced analysis: e.g. "1 falsifier rojo + macro favorable + good
  news → sigue aguantando".
- Sober Bloomberg-analyst tone.

Operational guarantees:
- `is_llm_available()` returns False when ANTHROPIC_API_KEY is unset.
- Every generator returns None on missing key / SDK / API error, so
  the caller can fall back to the deterministic rule-based path.
- The Anthropic SDK is imported lazily inside `_get_client()` so this
  module is safe to import even if `anthropic` is not installed.
"""

from __future__ import annotations

import os
from typing import Any

MODEL = "claude-sonnet-4-6"
MAX_TOKENS_NARRATIVE = 400
MAX_TOKENS_OPINION = 600


def is_llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client():
    """Lazy SDK import + client construction. Returns None when the
    SDK is missing or the API key is unset."""
    if not is_llm_available():
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    try:
        return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    except Exception:
        return None


# Public alias — analyst-side scripts (news_scanner, etc.) consume this
# instead of the underscore-prefixed name.
get_client = _get_client


def _classify_vix(vix: float | None) -> str:
    if vix is None:
        return "unknown"
    if vix < 15:
        return "calmo (risk-on)"
    if vix < 20:
        return "neutral"
    if vix < 30:
        return "elevado (cautela)"
    return "pánico (risk-off)"


# ----------------------------------------------------------------------
# Market state narrative
# ----------------------------------------------------------------------
MARKET_STATE_PROMPT = """Eres un analista financiero institucional con tono sobrio.

Datos de mercado:
- VIX: {vix}
- Clasificación VIX: {vix_class}
- Bond/Equity ratio 30d: {be_ratio:+.2f}%
- Money flow narrative determinístico: {money_flow}

Cartera del usuario:
- NAV total: EUR {nav}
- Posiciones activas: {positions_count}
- Cash disponible: EUR {cash}
- Health status: {health_status}

Genera un párrafo de 3-5 frases con tu opinión honesta directa:
1. Cómo está el mercado HOY (sin scores, sin probabilidades numéricas).
2. Qué implica para esta cartera específica (no genérico).
3. Una acción concreta o "sigue aguantando" si no hay nada que hacer.

Reglas estrictas:
- NO uses emojis ni emoticonos
- NO uses scores numéricos del estilo "82% confianza"
- NO digas "considerar A, B o C" — comprométete con UNA opinión
- Tono Bloomberg analyst: directo, profesional, sin adornos
- Máximo 4 frases

Responde solo con el párrafo, sin preámbulo ni conclusión."""


def generate_market_state_narrative(
    market_data: dict[str, Any], portfolio_data: dict[str, Any]
) -> str | None:
    client = _get_client()
    if client is None:
        return None
    try:
        prompt = MARKET_STATE_PROMPT.format(
            vix=market_data.get("vix", "N/A"),
            vix_class=_classify_vix(market_data.get("vix")),
            be_ratio=(market_data.get("bond_equity_ratio_30d", 0.0) or 0.0)
            * 100,
            money_flow=market_data.get("money_flow", "—"),
            nav=int(portfolio_data.get("nav_total_eur", 0) or 0),
            positions_count=portfolio_data.get("positions_count", 0),
            cash=int(portfolio_data.get("cash_eur", 0) or 0),
            health_status=portfolio_data.get("health_status", "—"),
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_NARRATIVE,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as e:  # noqa: BLE001 — fall back is the whole point
        print(f"LLM error (market_state): {e}")
        return None


# ----------------------------------------------------------------------
# Comparative analysis narrative
# ----------------------------------------------------------------------
COMPARATIVE_PROMPT = """Eres un analista de cartera con tono institucional sobrio.

Datos de las carteras (delta desde T0):
- Real: EUR {nav_real}, delta {delta_real:+.2f}%
- Shadow: EUR {nav_shadow}, delta {delta_shadow:+.2f}%
- Benchmark passive: EUR {nav_bench}, delta {delta_bench:+.2f}%
- Robo-advisor: EUR {nav_robo}, delta {delta_robo:+.2f}%

Comparador de hoy: {comparator}
Diferencia real vs {comparator}: {diff_pp:+.2f} pp

Genera análisis comparativo honesto en 4-5 frases:
1. ¿Va bien o no? Juicio directo.
2. ¿Por qué la diferencia con el comparador?
3. ¿Es ruido (diff <0.5pp en pocos días) o señal estructural?
4. Acción concreta. Si la diferencia es ruido, di "no toques nada".

Estructura tu respuesta así:
PRIMERA LÍNEA: un titular de 5-9 palabras.
SEGUNDA LÍNEA EN ADELANTE: el análisis.

Reglas:
- NO emojis, NO scores numéricos
- Tono directo, profesional, sin adornos
- Máximo 5 frases en el análisis"""


def generate_comparative_narrative(
    comparison_data: dict[str, Any],
) -> dict[str, str] | None:
    client = _get_client()
    if client is None:
        return None
    try:
        prompt = COMPARATIVE_PROMPT.format(
            nav_real=int(comparison_data.get("nav_real", 0) or 0),
            delta_real=comparison_data.get("delta_real_pct", 0.0) or 0.0,
            nav_shadow=int(comparison_data.get("nav_shadow", 0) or 0),
            delta_shadow=comparison_data.get("delta_shadow_pct", 0.0) or 0.0,
            nav_bench=int(comparison_data.get("nav_benchmark", 0) or 0),
            delta_bench=comparison_data.get("delta_benchmark_pct", 0.0) or 0.0,
            nav_robo=int(comparison_data.get("nav_robo", 0) or 0),
            delta_robo=comparison_data.get("delta_robo_pct", 0.0) or 0.0,
            comparator=comparison_data.get("comparator_today", "benchmark_passive"),
            diff_pp=comparison_data.get("diff_pp", 0.0) or 0.0,
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_OPINION,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        if not text:
            return None
        full = text.strip()
        lines = [ln.strip() for ln in full.split("\n", 1) if ln.strip()]
        if len(lines) >= 2:
            return {"headline": lines[0], "narrative": lines[1].strip()}
        return {"headline": "Análisis comparativo", "narrative": full}
    except Exception as e:  # noqa: BLE001
        print(f"LLM error (comparative): {e}")
        return None


# ----------------------------------------------------------------------
# Recommendation narrative refinement
# ----------------------------------------------------------------------
RECOMMENDATION_PROMPT = """Eres un asesor de inversiones con tono institucional sobrio.

Datos de la posición:
- Asset: {asset}
- Acción del sistema: {action_type}
- Override del usuario activo: {override_active}
- Posición actual: {position_pct:.2f}% NAV (EUR {position_eur})
- Confianza de la tesis: {confidence}
- Falsifiers en movimiento: {falsifier_in_motion}

Contexto de la tesis (resumen):
{context}

Genera narrative de 3-4 frases con opinión honesta directa:
1. Cómo está la posición HOY (sin scores ni "X% probabilidad").
2. Por qué la acción recomendada (o por qué respetar el override).
3. Acción específica (cantidad concreta o "mantén").

Reglas estrictas:
- NO emojis ni scores numéricos
- NO ofertas multi-choice ("considerar A o B"). Comprométete con UNA opinión.
- Si el análisis es matizado (ej. 1 falsifier rojo + macro favorable): explícitalo.
- Si el override está activo, respeta la decisión del usuario pero recuerda los riesgos.
- Máximo 4 frases.

Responde solo con el narrative, sin preámbulo."""


# ----------------------------------------------------------------------
# Position opinion (drill-down per ticker, enriched with 4 analyst inputs)
# ----------------------------------------------------------------------
POSITION_OPINION_PROMPT = """Eres un asesor de inversiones con tono institucional sobrio.

Datos de la posición:
- Asset: {asset}
- Peso actual: {weight_pct:.2f}% NAV (EUR {position_eur})
- Cost basis nativo: {cost_basis_native:.2f} {currency}
- Precio actual: {current_price:.2f} {currency}
- P&L latente: {pnl_eur:+.0f} EUR ({pnl_pct:+.2f}%)

Tesis vigente ({thesis_version}):
- Recomendación: {recommendation}
- Confianza: {confidence}
- Resumen: {thesis_summary}

Falsifiers ({n_falsifiers} en total):
{falsifiers_text}

Technicals:
- Trend: {trend}
- RSI(14): {rsi14} ({rsi_signal})
- MACD: {macd_signal}
- Bollinger: {bb_position}
- Precio vs MA50: {price_vs_ma50}
- Precio vs MA200: {price_vs_ma200}

Fundamentals:
- P/E trailing: {pe_ratio} | forward: {forward_pe}
- Operating margin: {operating_margin}
- Revenue growth y/y: {revenue_growth}
- Debt/Equity: {debt_to_equity}
- Sector: {sector}
- Analyst target: {target_price_str} (consenso: {recommendation_key})
- Red flags: {flags}

Noticias recientes ({n_news} items relevantes últimos 7 días):
{news_text}

Contexto adicional:
{additional_context}

Genera análisis honesto MATIZADO en 5-7 frases que integre los 4 inputs (tesis + technicals + fundamentals + news):
1. Cómo está la posición HOY combinando los 4 inputs.
2. Cuál input pesa más en tu juicio y POR QUÉ.
3. Por qué la opinión actual. Comprométete con UNA dirección.
4. Acción concreta (cantidad si aplica) o "no toques nada".
5. Si análisis matizado (e.g. fundamentals fuertes pero technicals bearish): explícalo en formato "sigue aguantando porque X aunque Y".

Reglas estrictas:
- NO emojis. NO scores numéricos. NO menús ("considerar A o B").
- COMPROMÉTETE con UNA opinión.
- Si tesis intacta + technicals neutros + sin news material: di "no toques nada".
- Si conflicto real entre inputs: explícalo en una sola frase.
- Si override usuario activo: respeta la decisión, recuerda los riesgos.

Responde solo con el análisis, sin preámbulo."""


def _format_falsifiers(falsifiers: list[dict[str, Any]]) -> str:
    status_icon = {
        "inactive": "OK",
        "halfway_activated": "MITAD",
        "activated": "ACTIVO",
        "active": "ACTIVO",
    }
    lines: list[str] = []
    for f in (falsifiers or [])[:5]:
        icon = status_icon.get(f.get("status", "unknown"), "?")
        name = f.get("name", "?")
        cur = f.get("current") or ""
        cur_str = f" (actual: {cur})" if cur else ""
        lines.append(
            f"  [{icon}] {name}: {f.get('status', 'unknown')}{cur_str}"
        )
    return "\n".join(lines) if lines else "Sin falsifiers definidos"


def _format_news(news: list[dict[str, Any]] | None) -> str:
    if not news:
        return "Sin noticias materiales recientes"
    lines: list[str] = []
    for n in news[:5]:
        relevance = (n.get("relevance") or "low").upper()
        summary = n.get("summary_1line") or (n.get("headline") or "")[:80]
        lines.append(f"  [{relevance}] {summary}")
    return "\n".join(lines)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_num(value: Any, fmt: str = "{:.2f}") -> str:
    if value is None:
        return "N/A"
    try:
        return fmt.format(float(value))
    except (TypeError, ValueError):
        return "N/A"


def generate_position_opinion(
    position: dict[str, Any],
    thesis: dict[str, Any],
    falsifiers: list[dict[str, Any]],
    additional_context: str = "",
    *,
    technicals: dict[str, Any] | None = None,
    fundamentals: dict[str, Any] | None = None,
    news: list[dict[str, Any]] | None = None,
) -> str | None:
    """LLM opinion on a single position. The four optional kwargs
    (`technicals`, `fundamentals`, `news`, `additional_context`) are the
    Fase 3A/B/C analyst inputs — when present, the prompt asks for a
    nuanced multi-input analysis; when absent, the prompt still works
    but degenerates to the original tesis-only narrative."""
    client = _get_client()
    if client is None:
        return None
    try:
        falsifiers_text = _format_falsifiers(falsifiers)

        cost_basis_native = float(position.get("cost_basis_native") or 0.0)
        quantity = float(position.get("quantity") or 0.0)
        cost_basis_per_share = (
            cost_basis_native / quantity if quantity > 0 else 0.0
        )
        current_price = float(position.get("current_price_native") or 0.0)
        position_eur = float(position.get("current_value_eur") or 0.0)
        weight_pct = float(position.get("weight_pct") or 0.0)
        pnl_eur = float(position.get("unrealized_pnl_eur") or 0.0)
        pnl_pct = (
            ((current_price / cost_basis_per_share) - 1.0) * 100.0
            if cost_basis_per_share > 0
            else 0.0
        )

        thesis_version = (
            thesis.get("version")
            or thesis.get("model_version")
            or thesis.get("thesis_version")
            or thesis.get("event_type", "thesis")
        )
        thesis_summary = (
            thesis.get("note")
            or thesis.get("confidence_justification")
            or thesis.get("reasoning")
            or "—"
        )[:500]

        # ---- Technicals (defaults preserve prompt structure when absent)
        tech = technicals or {}
        trend = tech.get("trend", "unknown")
        rsi14 = tech.get("rsi14", "N/A")
        rsi_signal = tech.get("rsi_signal", "unknown")
        macd_signal = tech.get("macd_signal", "unknown")
        bb_position = tech.get("bb_position", "unknown")
        ma50_v = tech.get("ma50")
        ma200_v = tech.get("ma200")
        price_t = tech.get("price")
        price_vs_ma50 = (
            f"{((price_t - ma50_v) / ma50_v * 100):+.1f}%"
            if ma50_v and price_t
            else "N/A"
        )
        price_vs_ma200 = (
            f"{((price_t - ma200_v) / ma200_v * 100):+.1f}%"
            if ma200_v and price_t
            else "N/A"
        )

        # ---- Fundamentals
        fund = fundamentals or {}
        pe_str = _fmt_num(fund.get("pe_ratio"), "{:.1f}")
        forward_pe_str = _fmt_num(fund.get("forward_pe"), "{:.1f}")
        op_margin_str = _fmt_pct(fund.get("operating_margin"))
        rev_growth_str = _fmt_pct(fund.get("revenue_growth"))
        de_str = _fmt_num(fund.get("debt_to_equity"), "{:.1f}")
        sector = fund.get("sector") or "N/A"
        target_price = fund.get("target_mean_price")
        target_price_str = (
            f"${target_price:.2f}" if isinstance(target_price, (int, float))
            else "N/A"
        )
        rec_key = fund.get("recommendation_key") or "N/A"
        flags_list = fund.get("flags") or []
        flags_str = ", ".join(flags_list) if flags_list else "ninguna"

        prompt = POSITION_OPINION_PROMPT.format(
            asset=position.get("ticker", "—"),
            weight_pct=weight_pct,
            position_eur=int(position_eur),
            cost_basis_native=cost_basis_per_share,
            current_price=current_price,
            currency=position.get("currency", "USD"),
            pnl_eur=pnl_eur,
            pnl_pct=pnl_pct,
            thesis_version=thesis_version,
            recommendation=(
                thesis.get("recommendation")
                or thesis.get("recommendation_v2")
                or "—"
            ),
            confidence=thesis.get("confidence_calibrated", "—"),
            thesis_summary=thesis_summary,
            n_falsifiers=len(falsifiers or []),
            falsifiers_text=falsifiers_text,
            trend=trend,
            rsi14=rsi14,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            bb_position=bb_position,
            price_vs_ma50=price_vs_ma50,
            price_vs_ma200=price_vs_ma200,
            pe_ratio=pe_str,
            forward_pe=forward_pe_str,
            operating_margin=op_margin_str,
            revenue_growth=rev_growth_str,
            debt_to_equity=de_str,
            sector=sector,
            target_price_str=target_price_str,
            recommendation_key=rec_key,
            flags=flags_str,
            n_news=len(news or []),
            news_text=_format_news(news),
            additional_context=(
                additional_context[:500]
                if additional_context
                else "Sin contexto adicional."
            ),
        )

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_OPINION,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as e:  # noqa: BLE001
        print(f"LLM error (position opinion): {e}")
        return None


def refine_recommendation_narrative(
    rec: dict[str, Any],
    position_data: dict[str, Any],
    context: str = "",
) -> str | None:
    client = _get_client()
    if client is None:
        return None
    try:
        prompt = RECOMMENDATION_PROMPT.format(
            asset=rec.get("asset", "—"),
            action_type=rec.get("type", "HOLD"),
            override_active=rec.get("type") == "HOLD_OVERRIDE",
            position_pct=float(position_data.get("weight_pct", 0.0) or 0.0),
            position_eur=int(position_data.get("current_value_eur", 0) or 0),
            confidence=rec.get("confidence", "—"),
            falsifier_in_motion=rec.get("falsifier_in_motion", False),
            context=context[:500] if context else "Sin contexto adicional.",
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_NARRATIVE,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as e:  # noqa: BLE001
        print(f"LLM error (recommendation {rec.get('asset')}): {e}")
        return None

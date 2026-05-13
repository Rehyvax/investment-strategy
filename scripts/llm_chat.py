"""Interactive chat with the cerebro, scoped to a recommendation or to
the whole portfolio. Phase 2D-2 of the dashboard pipeline.

Same fallback contract as `llm_narratives.py`: every function returns
None when ANTHROPIC_API_KEY is unset, the SDK is missing, or the API
errors out — so the caller can render a graceful "API key not
configured" state.

The dashboard reads ANTHROPIC_API_KEY in two ways:
- Local development: this module looks for the env var directly. The
  Streamlit page can call `load_env_for_chat()` once at start so the
  same .env loaded by the CLI is also visible to the live process.
- Streamlit Cloud: the operator pastes the key under [anthropic] in
  the Secrets panel; the page passes it via env at session start.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MODEL = "claude-sonnet-4-6"
MAX_TOKENS_CHAT = 600

CHAT_SYSTEM_PROMPT = """Eres un asesor financiero institucional respondiendo \
preguntas concretas del usuario sobre su cartera y las recomendaciones del sistema.

Tono: directo, profesional, sobrio. SIN emojis, SIN scores numéricos ("82% probabilidad"), \
SIN opciones múltiples ("considerar A, B o C").

Contexto operacional:
- Cartera real en Lightyear, ~19 posiciones.
- Spain LIRPF + FIFO + 2-month wash-sale rule activos.
- Holding actual con override consciente: AXON (gate Q2 2026).
- Watch activo: MELI hasta Q2 2026 (~6 agosto).

Reglas estrictas:
1. Comprométete con UNA opinión. NO digas "depende".
2. Si hay matiz: explícitalo ("sigue aguantando porque X aunque Y").
3. Si la pregunta pide número (vender / cuánto): da número concreto.
4. Si falta data: di EXACTAMENTE qué falta, no "más información".
5. Máximo 4-5 frases."""


def load_env_for_chat(root: Path | None = None) -> None:
    """Convenience helper so a long-running Streamlit page can pick up
    ANTHROPIC_API_KEY from .env without restarting the process."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    if root is None:
        root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")


def is_chat_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client():
    if not is_chat_available():
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    try:
        return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    except Exception:
        return None


def chat_about_recommendation(
    rec: dict[str, Any],
    user_question: str,
    portfolio_context: dict[str, Any],
) -> str | None:
    """Chat scoped to a single recommendation card."""
    client = _get_client()
    if client is None or not user_question.strip():
        return None
    nav = int(portfolio_context.get("nav_total_eur", 0) or 0)
    rec_block = (
        f"Recomendación actual del sistema sobre {rec.get('asset', '—')}:\n"
        f"- Acción: {rec.get('type', '—')}\n"
        f"- Titular: {rec.get('headline', '—')}\n"
        f"- Narrative del sistema: {rec.get('narrative', '—')}\n"
        f"- Acción concreta: {rec.get('action', '—')}\n"
        f"- Prioridad: {rec.get('priority', '—')}\n"
        f"- NAV total cartera: EUR {nav}"
    )
    user_msg = f"{rec_block}\n\nPregunta del usuario: {user_question.strip()}"
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_CHAT,
            system=CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as e:  # noqa: BLE001
        print(f"chat_about_recommendation error: {e}")
        return None


def chat_general(
    user_question: str,
    portfolio_context: dict[str, Any],
    cerebro_state: dict[str, Any] | None = None,
) -> str | None:
    """Free-form chat over the full cerebro state."""
    client = _get_client()
    if client is None or not user_question.strip():
        return None
    nav = int(portfolio_context.get("nav_total_eur", 0) or 0)
    parts = [
        f"NAV total cartera: EUR {nav}",
        f"Posiciones activas: {portfolio_context.get('positions_count', '—')}",
        f"Cash disponible: EUR {int(portfolio_context.get('cash_eur', 0) or 0)}",
    ]
    if cerebro_state:
        ms = cerebro_state.get("market_state") or {}
        if ms:
            parts.append(f"Régimen mercado: {ms.get('regime', 'unknown')}")
            parts.append(f"VIX: {ms.get('vix', '—')}")
        for alert in (cerebro_state.get("tax_alerts") or [])[:3]:
            parts.append(
                f"Tax alert: {alert.get('asset')} -> "
                f"{alert.get('message', '')[:120]}"
            )
    context = "\n".join(parts)
    user_msg = (
        f"Contexto actual:\n{context}\n\nPregunta: {user_question.strip()}"
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_CHAT,
            system=CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        return text.strip() if text else None
    except Exception as e:  # noqa: BLE001
        print(f"chat_general error: {e}")
        return None

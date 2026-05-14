"""Block D — Recommendations + chat ad-hoc per card.

Phase 2D-2: clicking 'Preguntar más' opens a contextual chat scoped to
the recommendation. Falls back to a disabled button with explanatory
help text when ANTHROPIC_API_KEY is not configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make `scripts/llm_chat` importable from this dashboard component.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from llm_chat import (  # noqa: E402
    chat_about_recommendation,
    is_chat_available,
    load_env_for_chat,
)
from styles import status_badge  # noqa: E402

ACTION_LABELS = {
    "BUY": "Comprar",
    "BUY_MORE": "Aumentar",
    "HOLD": "Mantener",
    "WATCH": "Vigilar",
    "REDUCE": "Reducir",
    "SELL": "Vender",
    "EXIT": "Salir",
    "HOLD_OVERRIDE": "Override Activo",
    "INFO": "Info",
}

PRIORITY_LABELS = {
    "high": "Prioridad Alta",
    "medium": "Prioridad Media",
    "low": "Prioridad Baja",
}


def render_recommendations(
    recs: list[dict],
    portfolio_context: dict | None = None,
) -> None:
    st.markdown("<h2>Recomendaciones</h2>", unsafe_allow_html=True)

    if not recs:
        st.info("Sin recomendaciones activas en este momento.")
        return

    portfolio_context = portfolio_context or {}
    # Pull .env into the live process so the deployed key reaches the
    # chat client when the Streamlit page first renders the card.
    load_env_for_chat()
    chat_enabled = is_chat_available()

    for rec in recs[:3]:
        action_label = ACTION_LABELS.get(rec["type"], rec["type"])
        priority_label = PRIORITY_LABELS.get(rec["priority"], rec["priority"])
        action_badge = status_badge(action_label, rec["color"])
        priority_badge = status_badge(priority_label, "neutral")
        source = rec.get("_narrative_source", "rule_based")
        source_badge = ""
        if source == "llm":
            source_badge = status_badge("LLM", "blue")

        st.markdown(
            f"""
            <div class="institutional-card">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
                    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                        {action_badge}
                        <span style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#E8ECF4; font-size:1.0625rem;">
                            {rec['asset']}
                        </span>
                        {source_badge}
                    </div>
                    {priority_badge}
                </div>
                <h3 style="font-size:1rem; color:#E8ECF4; margin:0 0 12px 0; font-weight:600;">{rec['headline']}</h3>
                <p style="color:#94A0B8; line-height:1.6; margin:0 0 16px 0; font-size:0.9375rem;">{rec['narrative']}</p>
                <div style="background:#1C2333; padding:10px 12px; border-radius:6px; margin-bottom:12px;">
                    <span style="font-size:0.75rem; color:#94A0B8; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Acción</span>
                    <p style="margin:4px 0 0 0; color:#E8ECF4; font-size:0.9375rem;">{rec['action']}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        rec_id = rec.get("id", rec["asset"])
        col1, col2, col3 = st.columns(3)
        col1.button(
            "Marcar ejecutada",
            key=f"exec_{rec_id}",
            use_container_width=True,
            type="secondary",
        )
        col2.button(
            "Posponer",
            key=f"defer_{rec_id}",
            use_container_width=True,
            type="secondary",
        )
        ask_clicked = col3.button(
            "Preguntar más",
            key=f"ask_{rec_id}",
            use_container_width=True,
            help=(
                "Cuesta tokens API (~0.01–0.02 USD por pregunta)."
                if chat_enabled
                else "API key no configurada (configure ANTHROPIC_API_KEY)."
            ),
            disabled=not chat_enabled,
        )
        if ask_clicked:
            st.session_state[f"chat_open_{rec_id}"] = True

        if chat_enabled and st.session_state.get(f"chat_open_{rec_id}"):
            _render_chat_panel(rec, rec_id, portfolio_context)


def _render_chat_panel(
    rec: dict, rec_id: str, portfolio_context: dict
) -> None:
    with st.expander(
        f"Preguntar sobre {rec['asset']}", expanded=True
    ):
        question = st.text_area(
            "Tu pregunta:",
            placeholder=(
                f"Ejemplo: ¿qué pasa si {rec['asset']} cae 10% antes de Q2?"
            ),
            key=f"question_{rec_id}",
            height=80,
        )
        cols = st.columns([1, 4])
        submit = cols[0].button(
            "Enviar pregunta", key=f"submit_{rec_id}", type="primary"
        )
        cols[1].caption("Coste estimado: ~$0.01–0.02 por pregunta.")

        if submit and question and question.strip():
            with st.spinner("Consultando…"):
                response = chat_about_recommendation(
                    rec, question, portfolio_context
                )
            if response:
                st.session_state[f"chat_answer_{rec_id}"] = response
            else:
                st.session_state[f"chat_answer_{rec_id}"] = (
                    "Error al consultar la API. Verifica la conexión y "
                    "ANTHROPIC_API_KEY."
                )

        answer = st.session_state.get(f"chat_answer_{rec_id}")
        if answer:
            st.markdown(
                f"""
                <div class="institutional-card" style="background:#F0F9FF; border-left: 3px solid #3B82F6; margin-top:12px;">
                    <span style="font-size:0.75rem; color:#3B82F6; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Respuesta del cerebro</span>
                    <p style="margin:8px 0 0 0; color:#E8ECF4; line-height:1.6; font-size:0.9375rem; white-space:pre-wrap;">{answer}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if st.button(
            "Cerrar",
            key=f"close_{rec_id}",
            type="secondary",
        ):
            st.session_state.pop(f"chat_open_{rec_id}", None)
            st.session_state.pop(f"chat_answer_{rec_id}", None)
            st.rerun()

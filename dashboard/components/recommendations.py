"""Block D — Recommendations (institutional cards, action/priority badges)."""

from __future__ import annotations

import streamlit as st

from styles import status_badge

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


def render_recommendations(recs: list[dict]) -> None:
    st.markdown("<h2>Recomendaciones</h2>", unsafe_allow_html=True)

    if not recs:
        st.info("Sin recomendaciones activas en este momento.")
        return

    for rec in recs[:3]:
        action_label = ACTION_LABELS.get(rec["type"], rec["type"])
        priority_label = PRIORITY_LABELS.get(rec["priority"], rec["priority"])
        action_badge = status_badge(action_label, rec["color"])
        priority_badge = status_badge(priority_label, "neutral")

        st.markdown(
            f"""
            <div class="institutional-card">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
                    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                        {action_badge}
                        <span style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#0F172A; font-size:1.0625rem;">
                            {rec['asset']}
                        </span>
                    </div>
                    {priority_badge}
                </div>
                <h3 style="font-size:1rem; color:#0F172A; margin:0 0 12px 0; font-weight:600;">{rec['headline']}</h3>
                <p style="color:#475569; line-height:1.6; margin:0 0 16px 0; font-size:0.9375rem;">{rec['narrative']}</p>
                <div style="background:#F1F5F9; padding:10px 12px; border-radius:6px; margin-bottom:12px;">
                    <span style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Acción</span>
                    <p style="margin:4px 0 0 0; color:#0F172A; font-size:0.9375rem;">{rec['action']}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)
        col1.button(
            "Marcar ejecutada",
            key=f"exec_{rec['id']}",
            use_container_width=True,
            type="secondary",
        )
        col2.button(
            "Posponer",
            key=f"defer_{rec['id']}",
            use_container_width=True,
            type="secondary",
        )
        col3.button(
            "Preguntar más",
            key=f"ask_{rec['id']}",
            use_container_width=True,
            help="Cuesta tokens API (Fase 2B+)",
        )

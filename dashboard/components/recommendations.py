"""Bloque D — Top 3 recommendations from the cerebro."""

from __future__ import annotations

import streamlit as st

PRIORITY_BADGE = {
    "high": "🔴 ALTA",
    "medium": "🟡 MEDIA",
    "low": "🟢 BAJA",
}
COLOR_PREFIX = {
    "green": "🟢",
    "yellow": "🟡",
    "orange": "🟠",
    "red": "🔴",
}


def render_recommendations(recs: list[dict]) -> None:
    st.subheader("Recomendaciones del cerebro")

    for rec in recs[:3]:
        prefix = COLOR_PREFIX.get(rec["color"], "⚪")
        badge = PRIORITY_BADGE.get(rec["priority"], rec["priority"])
        with st.container():
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"### {prefix} {rec['headline']}")
            col2.caption(badge)

            st.markdown(rec["narrative"])
            st.info(f"**Acción:** {rec['action']}")

            col1, col2, col3 = st.columns(3)
            col1.button("Marcar ejecutada", key=f"exec_{rec['id']}")
            col2.button("Posponer", key=f"defer_{rec['id']}")
            col3.button(
                "Preguntar más",
                key=f"ask_{rec['id']}",
                help="Cuesta tokens API (Fase 2B+)",
            )
            st.markdown("---")

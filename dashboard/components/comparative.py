"""Bloque E — Comparative analysis (rotating comparator)."""

from __future__ import annotations

import streamlit as st


def render_comparative(data: dict) -> None:
    st.subheader("Comparativa explicable")
    st.markdown(f"### {data['headline']}")
    st.write(data["narrative"])
    st.caption(
        f"Comparador rotativo de hoy: **{data['comparator_today']}** — "
        f"{data['comparator_reason']}"
    )
    st.success(f"**Acción sugerida:** {data['action']}")

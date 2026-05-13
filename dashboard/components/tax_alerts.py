"""Bloque B' — LIRPF / Spain tax rule alerts."""

from __future__ import annotations

import streamlit as st


def render_tax_alerts(alerts: list[dict]) -> None:
    st.subheader("LIRPF / Reglas fiscales")
    for alert in alerts:
        st.warning(
            f"**{alert['asset']}** ({alert.get('alert_type', 'alert')}): "
            f"{alert['message']}"
        )

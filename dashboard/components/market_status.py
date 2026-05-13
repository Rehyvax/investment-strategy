"""Bloque A — Market status: regime + money flow + fear gauge."""

from __future__ import annotations

import streamlit as st

COLOR_MAP = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def render_market_status(data: dict) -> None:
    st.subheader("Estado del mercado")

    col1, col2 = st.columns([1, 3])
    color = COLOR_MAP.get(data["regime_color"], "⚪")
    label = data["regime"].replace("_", " ").title()
    col1.markdown(f"## {color} {label}")
    col2.markdown("**EL CEREBRO LO VE ASÍ:**")
    col2.write(data["explanation"])

    st.markdown("**Hacia dónde se mueve el dinero**")
    st.info(data["money_flow"])

    col1, col2 = st.columns(2)
    col1.metric("VIX", data["vix"])
    col2.metric(
        "Bond/Equity ratio 30d", f"{data['bond_equity_ratio_30d'] * 100:+.1f}%"
    )
    st.caption(data["fear_summary"])

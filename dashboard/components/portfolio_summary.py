"""Bloque B — Portfolio real summary: NAV, deltas, health, drawdown, cash."""

from __future__ import annotations

import streamlit as st

HEALTH_COLOR = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def render_portfolio_summary(data: dict) -> None:
    st.subheader("Tu cartera real HOY")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("NAV total", f"€{data['nav_total_eur']:,.0f}")
    col2.metric("Delta 1D", f"{data['nav_delta_1d_pct']:+.2f}%")
    col3.metric("Delta 1M", f"{data['nav_delta_1m_pct']:+.2f}%")
    col4.metric("Delta YTD", f"{data['nav_delta_ytd_pct']:+.2f}%")

    color = HEALTH_COLOR.get(data["health_status"], "⚪")
    st.markdown(f"**Salud:** {color} {data['health_summary']}")

    col1, col2 = st.columns(2)
    col1.metric(
        "Drawdown actual",
        f"{data['drawdown_current_pct']:+.2f}%",
        help=f"Desde peak {data['drawdown_from_peak']}",
    )
    col2.metric(
        "Cash disponible",
        f"€{data['cash_eur']:,.0f}",
        f"{data['cash_pct_nav']:.1f}% NAV",
    )

    st.caption(f"{data['positions_count']} posiciones activas")

"""Block B — Portfolio real summary (institutional layout, no emojis)."""

from __future__ import annotations

import streamlit as st

from styles import format_currency_eur, format_percent, status_badge


def render_portfolio_summary(data: dict) -> None:
    st.markdown("<h2>Cartera Real</h2>", unsafe_allow_html=True)

    cols = st.columns(5)
    cols[0].metric("NAV Total", format_currency_eur(data["nav_total_eur"]))
    cols[1].metric("1D", format_percent(data["nav_delta_1d_pct"]))
    cols[2].metric("1S", format_percent(data["nav_delta_1w_pct"]))
    cols[3].metric("1M", format_percent(data["nav_delta_1m_pct"]))
    cols[4].metric("YTD", format_percent(data["nav_delta_ytd_pct"]))

    health_badge = status_badge(
        data["health_status"].upper(), data["health_status"]
    )
    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <span style="font-size:0.75rem; color:#94A0B8; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Estado</span>
                {health_badge}
            </div>
            <p style="font-size:0.9375rem; color:#94A0B8; margin:0;">{data['health_summary']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Drawdown desde peak",
        format_percent(data["drawdown_current_pct"]),
        help=f"Peak en {data['drawdown_from_peak']}",
    )
    col2.metric(
        "Cash disponible",
        format_currency_eur(data["cash_eur"]),
        f"{data['cash_pct_nav']:.1f}% NAV",
    )
    col3.metric("Posiciones activas", data["positions_count"])

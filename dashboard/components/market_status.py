"""Block A — Market status (institutional card layout, no emojis)."""

from __future__ import annotations

import streamlit as st

from styles import status_badge

REGIME_LABELS = {
    "risk_on_strong": "Risk-On Fuerte",
    "risk_on_moderate": "Risk-On Moderado",
    "neutral": "Neutral",
    "risk_off_moderate": "Risk-Off Moderado",
    "risk_off_strong": "Risk-Off Fuerte",
}


def render_market_status(data: dict) -> None:
    st.markdown("<h2>Estado del Mercado</h2>", unsafe_allow_html=True)

    regime_label = REGIME_LABELS.get(data["regime"], data["regime"])
    badge_html = status_badge(regime_label, data["regime_color"])

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                <span style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Régimen actual</span>
                {badge_html}
            </div>
            <p style="font-size:0.9375rem; color:#0F172A; line-height:1.6; margin:0;">{data['explanation']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;">Flujo de capital</div>
            <p style="font-size:0.9375rem; color:#0F172A; line-height:1.5; margin:0;">{data['money_flow']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "VIX",
            f"{data['vix']:.2f}",
            help="Volatilidad implícita S&P 500 a 30 días",
        )
    with col2:
        delta = data["bond_equity_ratio_30d"] * 100
        st.metric(
            "Bond/Equity ratio 30d",
            f"{delta:+.1f}%",
            help="Negativo = capital saliendo de bonos hacia equity",
        )
    st.caption(data["fear_summary"])

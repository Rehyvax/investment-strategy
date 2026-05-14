"""Block E — Comparative analysis (institutional card, no emoji)."""

from __future__ import annotations

import streamlit as st


def render_comparative(data: dict) -> None:
    st.markdown("<h2>Análisis Comparativo</h2>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="institutional-card" style="border-left: 3px solid #3B82F6;">
            <h3 style="margin:0 0 12px 0; color:#E8ECF4; font-size:1.125rem; font-weight:600;">{data['headline']}</h3>
            <p style="color:#94A0B8; line-height:1.6; margin:0 0 16px 0; font-size:0.9375rem;">{data['narrative']}</p>
            <div style="background:#131825; padding:12px; border-radius:6px; margin-bottom:12px;">
                <span style="font-size:0.75rem; color:#94A0B8; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">
                    Comparador del día: {data['comparator_today']}
                </span>
                <p style="margin:6px 0 0 0; color:#94A0B8; font-size:0.875rem;">{data['comparator_reason']}</p>
            </div>
            <div style="background:#1E3A5F; padding:12px; border-radius:6px;">
                <span style="font-size:0.75rem; color:#3B82F6; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Acción</span>
                <p style="margin:4px 0 0 0; color:#1E3A5F; font-weight:500; font-size:0.9375rem;">{data['action']}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

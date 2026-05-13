"""Block E — Comparative analysis (institutional card, no emoji)."""

from __future__ import annotations

import streamlit as st


def render_comparative(data: dict) -> None:
    st.markdown("<h2>Análisis Comparativo</h2>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="institutional-card" style="border-left: 3px solid #1E40AF;">
            <h3 style="margin:0 0 12px 0; color:#0F172A; font-size:1.125rem; font-weight:600;">{data['headline']}</h3>
            <p style="color:#475569; line-height:1.6; margin:0 0 16px 0; font-size:0.9375rem;">{data['narrative']}</p>
            <div style="background:#F8FAFC; padding:12px; border-radius:6px; margin-bottom:12px;">
                <span style="font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">
                    Comparador del día: {data['comparator_today']}
                </span>
                <p style="margin:6px 0 0 0; color:#475569; font-size:0.875rem;">{data['comparator_reason']}</p>
            </div>
            <div style="background:#DBEAFE; padding:12px; border-radius:6px;">
                <span style="font-size:0.75rem; color:#1E40AF; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Acción</span>
                <p style="margin:4px 0 0 0; color:#1E3A8A; font-weight:500; font-size:0.9375rem;">{data['action']}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

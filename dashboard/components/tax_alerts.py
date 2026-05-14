"""Block B' — LIRPF / Spain tax rule alerts (institutional card layout)."""

from __future__ import annotations

import streamlit as st

from styles import status_badge


def render_tax_alerts(alerts: list[dict]) -> None:
    if not alerts:
        return
    st.markdown("<h2>Alertas Fiscales (LIRPF)</h2>", unsafe_allow_html=True)

    for alert in alerts:
        asset_badge = status_badge(alert["asset"], "yellow")
        alert_type = alert.get("alert_type", "alert").replace("_", " ").title()
        expires = alert.get("expires", "—")
        st.markdown(
            f"""
            <div class="institutional-card" style="border-left: 3px solid #F59E0B;">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                    {asset_badge}
                    <span style="font-size:0.75rem; color:#94A0B8; text-transform:uppercase; letter-spacing:0.05em;">
                        {alert_type} · Expira {expires}
                    </span>
                </div>
                <p style="margin:0; color:#E8ECF4; font-size:0.9375rem; line-height:1.5;">{alert['message']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

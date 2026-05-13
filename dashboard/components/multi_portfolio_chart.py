"""Block C — Multi-portfolio chart (institutional palette + ranking)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

INSTITUTIONAL_PALETTE = [
    "#1E40AF",
    "#0891B2",
    "#15803D",
    "#B91C1C",
    "#A16207",
    "#6D28D9",
    "#0F766E",
    "#64748B",
    "#475569",
]


def render_chart(data: dict) -> None:
    st.markdown("<h2>Performance Comparativo</h2>", unsafe_allow_html=True)

    st.caption("Selecciona carteras a mostrar:")
    cols = st.columns(5)
    visible: dict[str, bool] = {}
    for i, series in enumerate(data["series"]):
        col = cols[i % 5]
        visible[series["name"]] = col.checkbox(
            series["name"],
            value=series.get("default_visible", False),
            key=f"toggle_{series['name']}",
        )

    fig = go.Figure()
    for i, series in enumerate(data["series"]):
        if not visible.get(series["name"], False):
            continue
        color = INSTITUTIONAL_PALETTE[i % len(INSTITUTIONAL_PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=data["labels"],
                y=series["values"],
                name=series["name"],
                line=dict(color=color, width=2),
                hovertemplate=(
                    f"<b>{series['name']}</b><br>%{{x}}<br>"
                    "Index: %{y:.2f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        yaxis_title="Index (T0=100)",
        xaxis_title="",
        hovermode="x unified",
        height=400,
        margin=dict(l=40, r=20, t=20, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", size=12, color="#475569"),
        xaxis=dict(
            gridcolor="#F1F5F9",
            linecolor="#E2E8F0",
            zerolinecolor="#E2E8F0",
        ),
        yaxis=dict(
            gridcolor="#F1F5F9",
            linecolor="#E2E8F0",
            zerolinecolor="#E2E8F0",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    sorted_series = sorted(
        [s for s in data["series"] if visible.get(s["name"], False)],
        key=lambda s: s["values"][-1],
        reverse=True,
    )
    if not sorted_series:
        return

    ranking_html = (
        '<div style="margin-top:8px;">'
        '<div style="font-size:0.75rem; color:#64748B; text-transform:uppercase;'
        ' letter-spacing:0.05em; font-weight:600; margin-bottom:8px;">Ranking</div>'
    )
    for i, series in enumerate(sorted_series, 1):
        delta = series["values"][-1] - 100
        color = (
            "#15803D"
            if delta > 0
            else ("#B91C1C" if delta < 0 else "#64748B")
        )
        ranking_html += (
            f'<div style="display:flex; justify-content:space-between;'
            f' padding:6px 0; border-bottom:1px solid #F1F5F9; font-size:0.875rem;">'
            f'<span style="color:#475569;">{i}. {series["name"]}</span>'
            f'<span style="font-family:\'JetBrains Mono\', monospace;'
            f' color:{color}; font-weight:600;">{delta:+.2f}%</span>'
            f"</div>"
        )
    ranking_html += "</div>"
    st.markdown(ranking_html, unsafe_allow_html=True)

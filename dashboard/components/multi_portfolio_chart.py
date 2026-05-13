"""Bloque C — Multi-portfolio chart (toggleable, normalized to T0=100)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_chart(data: dict) -> None:
    st.subheader("Comparativa carteras")

    st.markdown("**Carteras a mostrar:**")
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
    for series in data["series"]:
        if not visible.get(series["name"], False):
            continue
        fig.add_trace(
            go.Scatter(
                x=data["labels"],
                y=series["values"],
                name=series["name"],
                line=dict(color=series["color"]),
                hovertemplate=(
                    f"<b>{series['name']}</b><br>%{{x}}<br>%{{y:.2f}}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        yaxis_title="Index (T0=100)",
        xaxis_title="Fecha",
        hovermode="x unified",
        height=400,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Ranking:**")
    sorted_series = sorted(
        data["series"], key=lambda s: s["values"][-1], reverse=True
    )
    for i, series in enumerate(sorted_series, 1):
        delta = series["values"][-1] - 100
        st.write(f"{i}. **{series['name']}**: {delta:+.2f}%")

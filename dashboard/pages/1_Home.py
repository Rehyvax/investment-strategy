"""Pantalla 1 — Home Cockpit (institutional UI)."""

from __future__ import annotations

import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from components.comparative import render_comparative  # noqa: E402
from components.market_status import render_market_status  # noqa: E402
from components.multi_portfolio_chart import render_chart  # noqa: E402
from components.news_feed import render_news_feed  # noqa: E402
from components.portfolio_summary import render_portfolio_summary  # noqa: E402
from components.recommendations import render_recommendations  # noqa: E402
from components.tax_alerts import render_tax_alerts  # noqa: E402
from services.cerebro_state import load_cerebro_state  # noqa: E402
from styles import inject_css  # noqa: E402

st.set_page_config(
    page_title="Investment Dashboard", page_icon=":bar_chart:", layout="wide"
)

inject_css()

if not check_auth():
    st.stop()

state = load_cerebro_state()

st.markdown(
    "<h1 style='margin-bottom:0;'>Investment Dashboard</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
    f"Resumen del día · última actualización {state['generated_at']}</p>",
    unsafe_allow_html=True,
)

render_market_status(state["market_state"])
render_portfolio_summary(state["portfolio_real"])

if state.get("tax_alerts"):
    render_tax_alerts(state["tax_alerts"])

render_chart(state["portfolios_chart_data"])


# ----------------------------------------------------------------------
# Block — Salud Riesgo-Retorno (Fase 6 Parte B)
# ----------------------------------------------------------------------
def _render_risk_metrics(metrics: dict | None) -> None:
    st.markdown("<h2>Salud Riesgo-Retorno</h2>", unsafe_allow_html=True)
    if not isinstance(metrics, dict):
        st.caption("Métricas no disponibles aún.")
        return
    if metrics.get("status") == "insufficient_data":
        st.info(
            f"Métricas riesgo pendientes: {metrics.get('message', '')}. "
            "Estarán disponibles cuando haya >=10 días de retornos consecutivos."
        )
        return

    def _color_sharpe(v: float) -> str:
        if v >= 1.0:
            return "#10B981"
        if v >= 0.5:
            return "#F59E0B"
        return "#EF4444"

    def _color_sortino(v: float) -> str:
        if v >= 1.5:
            return "#10B981"
        if v >= 0.7:
            return "#F59E0B"
        return "#EF4444"

    def _color_dd(v: float) -> str:
        if v > -5.0:
            return "#10B981"
        if v > -10.0:
            return "#F59E0B"
        return "#EF4444"

    def _metric_card(label: str, value, color: str) -> str:
        display = "—" if value is None else value
        return (
            "<div style='text-align:center; padding:14px;'>"
            f"<div style='font-size:0.75rem; color:#94A0B8; text-transform:uppercase;"
            f" letter-spacing:0.05em; font-weight:600;'>{label}</div>"
            f"<div style='font-size:1.5rem; color:{color}; font-weight:600;"
            " font-family:\"JetBrains Mono\", monospace;'>"
            f"{display}</div></div>"
        )

    sharpe = metrics.get("sharpe")
    sortino = metrics.get("sortino")
    calmar = metrics.get("calmar")
    mdd = metrics.get("max_drawdown_pct")
    sharpe_html = _metric_card(
        "Sharpe 90d", sharpe,
        _color_sharpe(sharpe) if isinstance(sharpe, (int, float)) else "#94A0B8",
    )
    sortino_html = _metric_card(
        "Sortino 90d", sortino,
        _color_sortino(sortino) if isinstance(sortino, (int, float)) else "#94A0B8",
    )
    calmar_html = _metric_card("Calmar 90d", calmar, "#E8ECF4")
    mdd_html = _metric_card(
        "Max DD 90d",
        f"{mdd:.2f}%" if isinstance(mdd, (int, float)) else None,
        _color_dd(mdd) if isinstance(mdd, (int, float)) else "#94A0B8",
    )
    st.markdown(
        f"<div style='display:grid; grid-template-columns:repeat(4, 1fr); "
        f"gap:8px;'>{sharpe_html}{sortino_html}{calmar_html}{mdd_html}</div>",
        unsafe_allow_html=True,
    )
    cagr = metrics.get("cagr_estimated_pct")
    n_obs = metrics.get("n_observations")
    st.caption(
        f"n={n_obs} días · CAGR estimado: "
        f"{cagr if cagr is not None else '—'}%"
    )


_render_risk_metrics(state.get("risk_metrics_real_90d"))


render_recommendations(state["recommendations"], state.get("portfolio_real", {}))
render_comparative(state["comparative_analysis"])
render_news_feed(state["news_feed"])

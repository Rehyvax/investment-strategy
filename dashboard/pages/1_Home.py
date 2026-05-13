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
    f"<p style='color:#64748B; margin-top:4px; font-size:0.9375rem;'>"
    f"Resumen del día · última actualización {state['generated_at']}</p>",
    unsafe_allow_html=True,
)

render_market_status(state["market_state"])
render_portfolio_summary(state["portfolio_real"])

if state.get("tax_alerts"):
    render_tax_alerts(state["tax_alerts"])

render_chart(state["portfolios_chart_data"])
render_recommendations(state["recommendations"], state.get("portfolio_real", {}))
render_comparative(state["comparative_analysis"])
render_news_feed(state["news_feed"])

"""Pantalla 1 — Home Cockpit.

Renders 6 blocks (A–F) consuming the cerebro state JSON. Each block is
a small module under `components/` so the page itself is just glue.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the dashboard root importable when Streamlit launches the page
# as a top-level script.
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

st.set_page_config(
    page_title="Home Cockpit", page_icon=":house:", layout="wide"
)

if not check_auth():
    st.stop()

state = load_cerebro_state()

st.title("Home Cockpit")
st.caption(f"Última actualización: {state['generated_at']}")
st.markdown("---")

# Block A — Market status
render_market_status(state["market_state"])
st.markdown("---")

# Block B — Portfolio real summary
render_portfolio_summary(state["portfolio_real"])
st.markdown("---")

# Block B' — Tax alerts (only when present)
if state.get("tax_alerts"):
    render_tax_alerts(state["tax_alerts"])
    st.markdown("---")

# Block C — Multi-portfolio chart
render_chart(state["portfolios_chart_data"])
st.markdown("---")

# Block D — Recommendations
render_recommendations(state["recommendations"])
st.markdown("---")

# Block E — Comparative analysis
render_comparative(state["comparative_analysis"])
st.markdown("---")

# Block F — News feed
render_news_feed(state["news_feed"])

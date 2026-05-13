"""Investment Dashboard — Streamlit entry point.

Phase 2A: hosts Pantalla 1 Home Cockpit. Future pantallas land as
additional files in `pages/` (Streamlit auto-discovers them).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from styles import inject_css  # noqa: E402

st.set_page_config(
    page_title="Investment Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

if not check_auth():
    st.stop()

st.sidebar.markdown(
    "<div style='font-weight:600; font-size:1rem; color:#0F172A;"
    " padding:0.5rem 0;'>Investment Lab</div>",
    unsafe_allow_html=True,
)
st.sidebar.caption("Pantallas en el menú lateral")
st.sidebar.markdown(
    "<div style='margin-top:1rem'></div>", unsafe_allow_html=True
)
st.sidebar.button(
    "Iniciar evaluación",
    help="Regenera state del cerebro on-demand (cuesta tokens API). "
    "Disponible en Fase 2B+.",
    disabled=True,
)
st.sidebar.caption("Última evaluación: ver Home → header")

st.switch_page("pages/1_Home.py")

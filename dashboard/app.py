"""Investment Dashboard — Streamlit entry point.

Phase 2A: hosts Pantalla 1 Home Cockpit. Future pantallas land as
additional files in `pages/` (Streamlit auto-discovers them).
"""

from __future__ import annotations

import streamlit as st

from auth import check_auth

st.set_page_config(
    page_title="Investment Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not check_auth():
    st.stop()

st.sidebar.title("Investment Lab")
st.sidebar.markdown("---")
st.sidebar.markdown("**Selecciona pantalla**")
st.sidebar.caption("Las pantallas están en el menú lateral arriba.")
st.sidebar.markdown("---")
st.sidebar.button(
    "Iniciar evaluación",
    help="Regenera state del cerebro on-demand (cuesta tokens API). "
    "Disponible en Fase 2B+.",
    disabled=True,
)
st.sidebar.caption("Última evaluación: ver Home → header")

# Redirect to the home page so opening / lands directly on Pantalla 1.
st.switch_page("pages/1_Home.py")

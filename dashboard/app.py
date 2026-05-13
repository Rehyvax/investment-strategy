"""Investment Dashboard — Streamlit entry point."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from services.cerebro_state import DEFAULT_STATE_PATH  # noqa: E402
from styles import inject_css  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(
    page_title="Investment Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

if not check_auth():
    st.stop()

# ----------------------------------------------------------------------
# Sidebar — sober nav + on-demand cerebro regeneration
# ----------------------------------------------------------------------
st.sidebar.markdown(
    "<div style='font-weight:600; font-size:1rem; color:#0F172A;"
    " padding:0.5rem 0;'>Investment Lab</div>",
    unsafe_allow_html=True,
)
st.sidebar.caption("Pantallas en el menú lateral")
st.sidebar.markdown(
    "<div style='margin-top:1rem'></div>", unsafe_allow_html=True
)


def _format_last_update() -> str:
    if not DEFAULT_STATE_PATH.exists():
        return "Sin datos"
    ts = datetime.fromtimestamp(DEFAULT_STATE_PATH.stat().st_mtime)
    return ts.strftime("%Y-%m-%d %H:%M")


if st.sidebar.button(
    "Iniciar evaluación",
    help=(
        "Regenera el cerebro on-demand vía Anthropic API. "
        "Coste aproximado: 0,10 USD por evaluación."
    ),
    type="primary",
):
    with st.sidebar:
        with st.spinner("Regenerando análisis…"):
            try:
                result = subprocess.run(
                    [sys.executable, "scripts/generate_cerebro_state.py"],
                    capture_output=True,
                    text=True,
                    cwd=str(PROJECT_ROOT),
                    timeout=180,
                )
                if result.returncode == 0:
                    st.success("Cerebro actualizado.")
                    st.rerun()
                else:
                    st.error(
                        f"Error al regenerar: {result.stderr[:200]}"
                    )
            except subprocess.TimeoutExpired:
                st.error("Timeout (180s). Revisa logs/cerebro_daily.log.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Error: {e}")

st.sidebar.markdown(
    "<div style='margin-top:1rem'></div>", unsafe_allow_html=True
)
st.sidebar.caption(f"Última actualización: {_format_last_update()}")

st.switch_page("pages/1_Home.py")

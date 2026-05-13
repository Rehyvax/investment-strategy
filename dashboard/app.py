"""Investment Dashboard — Streamlit entry point."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import json  # noqa: E402

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


# ----------------------------------------------------------------------
# Sidebar — Brier score (Fase 3E reflection loop output)
# ----------------------------------------------------------------------
def _render_brier_widget() -> None:
    if not DEFAULT_STATE_PATH.exists():
        return
    try:
        state = json.loads(DEFAULT_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    brier = state.get("brier_score_30d")
    n_eval = int(state.get("brier_n_evaluations_30d") or 0)
    st.sidebar.markdown(
        "<div style='margin-top:1rem'></div>", unsafe_allow_html=True
    )
    if brier is None or n_eval == 0:
        st.sidebar.caption(
            "Brier scoring pending — debates need 7+ days to mature."
        )
        return
    if brier >= 0.60:
        color = "#15803D"
    elif brier >= 0.50:
        color = "#A16207"
    else:
        color = "#B91C1C"
    st.sidebar.markdown(
        f"""
        <div style="background:#F8FAFC; padding:10px; border-radius:6px;
                    border-left:3px solid {color};">
            <div style="font-size:0.7rem; color:#64748B;
                        text-transform:uppercase; letter-spacing:0.05em;
                        font-weight:600;">Brier Score (30d)</div>
            <div style="font-family:'JetBrains Mono', monospace;
                        color:{color}; font-size:1.25rem; font-weight:600;">
                {brier:.3f}
            </div>
            <div style="font-size:0.7rem; color:#64748B;">n={n_eval}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_render_brier_widget()

st.switch_page("pages/1_Home.py")

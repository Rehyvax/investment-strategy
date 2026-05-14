"""Investment Dashboard — Streamlit entry point."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import json  # noqa: E402

import streamlit as st  # noqa: E402

# `auth` runs `_bootstrap_env_once()` at import time, so the
# ANTHROPIC_API_KEY (and any future secret) is populated in os.environ
# before any downstream module reads it. Importing here therefore
# satisfies a hidden dependency: do not move below other imports that
# call into `scripts.llm_*` or read `os.environ` at module level.
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


# ----------------------------------------------------------------------
# Sidebar — Acciones manuales (weekly debate sweep, user-controlled)
#
# Auto cron is intentionally NOT installed for the weekly debate. Spend
# is gated behind a two-step confirmation here so the user always sees
# the cost estimate before triggering the LangGraph batch.
# ----------------------------------------------------------------------
SWEEPS_LOG = PROJECT_ROOT / "data" / "events" / "weekly_sweeps.jsonl"
COST_PER_DEBATE_USD = 0.18  # keep aligned with run_weekly_debates.py


def _read_state_for_sidebar() -> dict:
    if not DEFAULT_STATE_PATH.exists():
        return {}
    try:
        return json.loads(DEFAULT_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _read_last_sweep() -> dict | None:
    if not SWEEPS_LOG.exists():
        return None
    try:
        lines = [
            ln for ln in SWEEPS_LOG.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    except OSError:
        return None
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def _render_last_sweep_info() -> None:
    sweep = _read_last_sweep()
    if not sweep:
        st.sidebar.caption("Sin barridos ejecutados todavía.")
        return
    ts_raw = sweep.get("timestamp", "")
    try:
        sweep_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        days_ago = (
            datetime.now(sweep_dt.tzinfo) - sweep_dt
        ).days
    except (TypeError, ValueError):
        days_ago = None
    n_run = int(sweep.get("debates_run") or 0)
    cost = float(sweep.get("estimated_cost_usd") or 0.0)
    if days_ago is None:
        color = "#64748B"
        age_label = "—"
    elif days_ago <= 7:
        color = "#15803D"
        age_label = f"hace {days_ago}d"
    elif days_ago <= 14:
        color = "#A16207"
        age_label = f"hace {days_ago}d"
    else:
        color = "#B91C1C"
        age_label = f"hace {days_ago}d"
    st.sidebar.markdown(
        f"""
        <div style="font-size:0.75rem; color:#64748B; margin-bottom:8px;">
            Último barrido:
            <span style="color:{color}; font-weight:600;">{age_label}</span><br>
            {n_run} debates · ${cost:.2f}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sweep_button() -> None:
    state = _read_state_for_sidebar()
    n_positions = int(
        (state.get("portfolio_real") or {}).get("positions_count") or 0
    )
    if n_positions == 0:
        n_positions = 19  # fallback expected size
    estimated_cost = round(n_positions * COST_PER_DEBATE_USD, 2)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Acciones manuales**")
    _render_last_sweep_info()

    if "weekly_sweep_confirm" not in st.session_state:
        st.session_state.weekly_sweep_confirm = False

    if not st.session_state.weekly_sweep_confirm:
        clicked = st.sidebar.button(
            "Ejecutar barrido semanal",
            help=(
                f"Lanza un debate Bull/Bear para las {n_positions} "
                f"posiciones del portfolio real. Coste estimado "
                f"${estimated_cost:.2f}."
            ),
            use_container_width=True,
            key="open_sweep_confirm",
        )
        if clicked:
            st.session_state.weekly_sweep_confirm = True
            st.rerun()
        return

    # Confirmation panel
    st.sidebar.markdown(
        f"""
        <div style="background:#FEF3C7; padding:12px; border-radius:6px;
                    border-left:3px solid #D97706; margin-bottom:8px;">
            <div style="font-size:0.75rem; color:#92400E; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.05em;">
                Confirmar barrido
            </div>
            <p style="margin:8px 0 4px 0; font-size:0.85rem; color:#451A03;">
                Ejecutará <strong>{n_positions} debates</strong> Bull vs Bear.<br>
                Coste estimado: <strong>~${estimated_cost:.2f}</strong>
            </p>
            <p style="margin:4px 0 0 0; font-size:0.75rem; color:#78350F;">
                Tiempo: 8-15 min · Se persistirán todos los verdicts
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.sidebar.columns(2)
    with col1:
        confirmed = st.button(
            "Confirmar",
            type="primary",
            use_container_width=True,
            key="confirm_sweep",
        )
    with col2:
        cancelled = st.button(
            "Cancelar", use_container_width=True, key="cancel_sweep"
        )

    if cancelled:
        st.session_state.weekly_sweep_confirm = False
        st.rerun()

    if confirmed:
        with st.sidebar:
            with st.spinner(f"Ejecutando {n_positions} debates (8-15 min)…"):
                ok = False
                err: str = ""
                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "scripts/run_weekly_debates.py",
                            "--weekly-sweep",
                        ],
                        capture_output=True,
                        text=True,
                        cwd=str(PROJECT_ROOT),
                        timeout=1200,  # 20 min hard cap
                    )
                    if result.returncode == 0:
                        ok = True
                    else:
                        err = (result.stderr or result.stdout)[-400:]
                except subprocess.TimeoutExpired:
                    err = "Timeout (20 min). Revisa logs/weekly_debates.log."
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
            if ok:
                # Auto-regenerate cerebro so the new debates surface
                # in Pantalla 3 immediately. Best-effort — we keep the
                # success message even if regen fails.
                with st.spinner("Refrescando cerebro…"):
                    try:
                        subprocess.run(
                            [sys.executable, "scripts/generate_cerebro_state.py"],
                            cwd=str(PROJECT_ROOT),
                            timeout=300,
                            capture_output=True,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                st.success("Barrido completado. Cerebro refrescado.")
            else:
                st.error(f"Error: {err[:300] if err else 'unknown'}")
        st.session_state.weekly_sweep_confirm = False
        st.rerun()


_render_sweep_button()


st.switch_page("pages/1_Home.py")

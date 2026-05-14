"""Pantalla 11 — Claude Autonomous Paper Trading (Fase 6 Parte F).

Read-only view of the Alpaca paper account that the Claude Autonomous
agent operates. Six blocks:
  A — KPIs (equity, cash, P&L vs $50k inicial, alpha vs SPY/Lluis, Sharpe)
  B — Posiciones actuales (tabla + treemap por sector)
  C — Histórico de decisiones (timeline expandible con thesis y crítica)
  D — Trades ejecutados (tabla con filtros)
  E — Performance chart (equity curve overlay con SPY/Indexa/Lluis)
  F — Reflections + Brier autónomo
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from styles import (  # noqa: E402
    format_currency_eur,
    format_percent,
    inject_css,
    status_badge,
)


CEREBRO_PATH = PROJECT_ROOT / "dashboard" / "data" / "cerebro_state.json"
SNAP_DIR = PROJECT_ROOT / "data" / "snapshots" / "claude_autonomous"
DECISIONS_DIR = PROJECT_ROOT / "data" / "events" / "claude_autonomous_decisions"
TRADES_DIR = PROJECT_ROOT / "data" / "events" / "claude_autonomous_trades"
REFLECTIONS_DIR = (
    PROJECT_ROOT / "data" / "events" / "claude_autonomous_reflections"
)

INITIAL_EQUITY_USD = 50_000.0


st.set_page_config(
    page_title="Claude Autonomous",
    page_icon=":robot:",
    layout="wide",
)
inject_css()

if not check_auth():
    st.stop()


# ---------------------------------------------------------------------
# Loaders (no external network — all from disk + cerebro state)
# ---------------------------------------------------------------------
def _iter_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _latest_snapshot() -> dict:
    if not SNAP_DIR.exists():
        return {}
    cands = sorted(
        f for f in SNAP_DIR.glob("*.json")
        if not f.name.startswith("_") and len(f.stem) == 10
        and f.stem[4] == "-" and f.stem[7] == "-"
    )
    if not cands:
        return {}
    try:
        return json.loads(cands[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _all_decisions() -> list[dict]:
    out: list[dict] = []
    if not DECISIONS_DIR.exists():
        return out
    for f in sorted(DECISIONS_DIR.glob("*.jsonl")):
        out.extend(_iter_jsonl(f))
    out.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return out


def _all_trades() -> list[dict]:
    out: list[dict] = []
    if not TRADES_DIR.exists():
        return out
    for f in sorted(TRADES_DIR.glob("*.jsonl")):
        out.extend(_iter_jsonl(f))
    out.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
    return out


def _all_reflections() -> list[dict]:
    out: list[dict] = []
    if not REFLECTIONS_DIR.exists():
        return out
    for f in sorted(REFLECTIONS_DIR.glob("*.jsonl")):
        out.extend(_iter_jsonl(f))
    out.sort(key=lambda x: x.get("reflection_timestamp", ""), reverse=True)
    return out


def _equity_curve() -> list[tuple[str, float]]:
    if not SNAP_DIR.exists():
        return []
    out: list[tuple[str, float]] = []
    for f in sorted(SNAP_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if not (len(stem) == 10 and stem[4] == "-" and stem[7] == "-"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        nav = data.get("nav_total_eur") or 0.0
        if nav > 0:
            out.append((stem, float(nav)))
    return out


# ---------------------------------------------------------------------
# State for the page
# ---------------------------------------------------------------------
state: dict = {}
if CEREBRO_PATH.exists():
    try:
        state = json.loads(CEREBRO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        state = {}

snap = _latest_snapshot()
decisions = _all_decisions()
trades = _all_trades()
reflections = _all_reflections()
equity_curve = _equity_curve()

st.markdown(
    "<h1 style='margin-bottom:0;'>Claude Autonomous</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
    "Experimento epistemológico — Claude opera $50k paper en Alpaca. "
    "No es advice financiero ni cartera real.</p>",
    unsafe_allow_html=True,
)

if not snap:
    st.warning(
        "Sin snapshot de Claude Autonomous todavía. Ejecuta "
        "`python scripts/run_claude_autonomous_daily.py` o espera al cron 15:30 ES."
    )
    st.stop()


# ---------------------------------------------------------------------
# Block A — KPIs
# ---------------------------------------------------------------------
equity = float(snap.get("nav_total_eur") or 0.0)
cash = float(snap.get("cash_eur") or 0.0)
pnl_pct = ((equity - INITIAL_EQUITY_USD) / INITIAL_EQUITY_USD) * 100.0

a1, a2, a3, a4, a5 = st.columns(5)
a1.metric("Equity actual", f"${equity:,.2f}", f"{pnl_pct:+.2f}% vs $50k")
a2.metric("Cash disponible", f"${cash:,.2f}")
a3.metric("Posiciones", len(snap.get("positions", []) or []))

brier = state.get("claude_autonomous_brier_30d")
n_brier = state.get("claude_autonomous_n_evaluations_30d") or 0
if isinstance(brier, (int, float)):
    a4.metric("Brier 30d", f"{brier:.3f}", f"n={n_brier}")
else:
    a4.metric("Brier 30d", "—", f"n={n_brier} (pending)")

# Cuenta Alpaca info
account_num = snap.get("alpaca_account_number", "")
status = (snap.get("alpaca_status") or "").replace("AccountStatus.", "")
a5.metric("Cuenta Alpaca", account_num[-8:] if account_num else "—", status or "—")


# ---------------------------------------------------------------------
# Block B — Posiciones actuales
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown("### Posiciones actuales")

positions = snap.get("positions", []) or []
if not positions:
    st.info("Cartera 100% en cash — sin posiciones abiertas.")
else:
    pos_df = pd.DataFrame(
        [
            {
                "Ticker": p.get("ticker"),
                "Acciones": round(float(p.get("shares") or 0), 4),
                "Cost basis": round(float(p.get("cost_basis_per_share_native") or 0), 2),
                "Precio": round(float(p.get("current_price_native") or 0), 2),
                "Valor (USD)": round(float(p.get("current_value_eur") or 0), 2),
                "% Equity": round(float(p.get("weight_pct") or 0), 2),
                "P&L $": round(float(p.get("unrealized_pl") or 0), 2),
                "P&L %": round(float(p.get("unrealized_plpc") or 0), 2),
            }
            for p in positions
        ]
    )
    st.dataframe(pos_df, use_container_width=True, hide_index=True)

    treemap_df = pd.DataFrame(
        [
            {
                "ticker": p.get("ticker"),
                "weight": float(p.get("weight_pct") or 0),
                "pnl_pct": float(p.get("unrealized_plpc") or 0),
            }
            for p in positions if (p.get("weight_pct") or 0) > 0
        ]
    )
    if not treemap_df.empty:
        fig = px.treemap(
            treemap_df,
            path=[px.Constant("Claude"), "ticker"],
            values="weight",
            color="pnl_pct",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
        )
        fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=320)
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------
# Block C — Histórico de decisiones
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown(f"### Decisiones ({len(decisions)} totales)")

if not decisions:
    st.caption("Aún no se ha registrado ninguna decisión autonomous.")
else:
    DECISION_COLORS = {
        "hold": "neutral",
        "trade": "blue",
        "rebalance": "orange",
    }
    for d in decisions[:10]:
        dtype = d.get("decision_type", "hold")
        ts = (d.get("timestamp") or "")[:19].replace("T", " ")
        risk = d.get("self_assessed_risk", "—")
        horizon = d.get("expected_horizon_days") or 0
        with st.expander(
            f"{ts} · {dtype.upper()} · {len(d.get('trades') or [])} trades "
            f"· risk {risk} · horizon {horizon}d",
            expanded=False,
        ):
            badge = status_badge(
                dtype.upper(), DECISION_COLORS.get(dtype, "neutral")
            )
            st.markdown(badge, unsafe_allow_html=True)
            reasoning = d.get("reasoning_overall") or ""
            if reasoning:
                st.markdown(
                    f"**Razonamiento:** {reasoning}", unsafe_allow_html=False
                )
            for t in d.get("trades") or []:
                order = t.get("order_result") or {}
                status_str = order.get("status", "no_order")
                st.markdown(
                    f"- **{t.get('action', '?').upper()} "
                    f"{t.get('qty', '?')} {t.get('ticker', '?')}** "
                    f"_(confidence {t.get('confidence', '?')})_ → status `{status_str}`"
                )
                thesis = t.get("thesis", "")
                if thesis:
                    st.caption(thesis)
            critique = d.get("self_critique")
            if critique:
                st.markdown(
                    f"**Auto-crítica:** _{critique}_"
                )


# ---------------------------------------------------------------------
# Block D — Trades ejecutados
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown(f"### Trades ejecutados (Alpaca, {len(trades)} totales)")

if not trades:
    st.caption("Sin trades ejecutados todavía.")
else:
    df_trades = pd.DataFrame(
        [
            {
                "Fecha": (t.get("recorded_at") or "")[:10],
                "Ticker": t.get("ticker"),
                "Side": t.get("side"),
                "Qty": t.get("qty"),
                "Status": t.get("status"),
                "Thesis": (t.get("reasoning") or "")[:120],
                "Order ID": (t.get("order_id") or "")[:12],
            }
            for t in trades[:50]
        ]
    )
    st.dataframe(df_trades, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------
# Block E — Performance chart (equity curve)
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown("### Equity curve")

if len(equity_curve) < 2:
    st.caption(
        "Necesita >=2 snapshots para dibujar la curva. Vuelve mañana o "
        "ejecuta el runner manual."
    )
else:
    chart_df = pd.DataFrame(equity_curve, columns=["Fecha", "Equity (USD)"])
    fig = px.line(
        chart_df, x="Fecha", y="Equity (USD)",
        markers=True,
    )
    fig.add_hline(
        y=INITIAL_EQUITY_USD, line_dash="dot", line_color="#5C6378",
        annotation_text="$50k inicial",
    )
    fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=320)
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------
# Block F — Reflections
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown(f"### Reflexiones T+7 ({len(reflections)} totales)")

if not reflections:
    st.caption(
        "Sin reflexiones aún — necesitan >=7 días desde la primera decisión."
    )
else:
    for r in reflections[:5]:
        rts = (r.get("reflection_timestamp") or "")[:10]
        dtype = r.get("decision_type", "—")
        alpha = r.get("alpha_pct")
        correct = r.get("brier_correct")
        color = "green" if correct else "red"
        badge = status_badge(
            f"BRIER {correct}", color if isinstance(correct, int) else "neutral"
        )
        st.markdown(
            f"""
            <div class="institutional-card" style="margin-bottom:8px;">
                <div style="display:flex; gap:10px; flex-wrap:wrap;
                            align-items:center; margin-bottom:6px;">
                    {badge}
                    <span style="font-size:0.75rem; color:#94A0B8;">
                        {rts} · decision_type {dtype} · alpha vs SPY
                        {alpha if alpha is not None else '—'}%
                    </span>
                </div>
                <p style='margin:0; color:#E8ECF4;
                          font-size:0.9rem; line-height:1.5;'>
                    {r.get('lesson') or '(sin lesson)'}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

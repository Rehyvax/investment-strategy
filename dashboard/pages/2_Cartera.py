"""Pantalla 2 — Cartera Real (full holdings view + concentrations + bulk actions)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from services.portfolio_reader import PortfolioReader  # noqa: E402
from styles import (  # noqa: E402
    format_currency_eur,
    format_percent,
    inject_css,
    status_badge,
)


st.set_page_config(
    page_title="Cartera Real",
    page_icon=":briefcase:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

if not check_auth():
    st.stop()


reader = PortfolioReader()
kpis = reader.get_kpis()
positions = reader.get_enriched_positions()
concentrations = reader.get_concentrations()


# ----------------------------------------------------------------------
# Block A — Header KPIs
# ----------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0;'>Cartera Real</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
    f"Snapshot {kpis.get('as_of_date') or '—'} · "
    f"{kpis['n_positions']} posiciones</p>",
    unsafe_allow_html=True,
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("NAV total", format_currency_eur(kpis["nav_total_eur"], 2))
c2.metric(
    "Cash",
    format_currency_eur(kpis["cash_eur"], 2),
    f"{kpis['cash_pct_nav']:.1f}% NAV",
)
c3.metric("Posiciones", kpis["n_positions"])
unrealized = kpis["unrealized_pnl_eur"]
c4.metric(
    "P&L latente",
    format_currency_eur(unrealized, 2),
    f"{(unrealized / kpis['nav_total_eur'] * 100) if kpis['nav_total_eur'] else 0:+.2f}%",
)
realized = kpis["realized_pnl_ytd_eur"]
c5.metric(
    "P&L realizado YTD",
    format_currency_eur(realized, 2),
)


# ----------------------------------------------------------------------
# Block B — Filters + table
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### Holdings")

if not positions:
    st.warning("Sin snapshot real disponible.")
    st.stop()

sectors_all = sorted({p["sector"] for p in positions})
countries_all = sorted({p["country"] for p in positions})
verdicts_all = sorted({p["debate_verdict"] for p in positions})

fc1, fc2, fc3 = st.columns(3)
sel_sectors = fc1.multiselect(
    "Sector", options=sectors_all, default=sectors_all
)
sel_countries = fc2.multiselect(
    "País", options=countries_all, default=countries_all
)
sel_verdicts = fc3.multiselect(
    "Debate verdict", options=verdicts_all, default=verdicts_all
)
weight_max = max((p["weight_pct"] for p in positions), default=20.0)
weight_range = st.slider(
    "Rango weight % NAV",
    min_value=0.0,
    max_value=float(max(weight_max, 1.0)),
    value=(0.0, float(max(weight_max, 1.0))),
    step=0.5,
    format="%.1f%%",
)

filtered = [
    p for p in positions
    if p["sector"] in sel_sectors
    and p["country"] in sel_countries
    and p["debate_verdict"] in sel_verdicts
    and weight_range[0] <= p["weight_pct"] <= weight_range[1]
]

if not filtered:
    st.info("Ninguna posición cumple los filtros activos.")
else:
    df = pd.DataFrame(
        [
            {
                "Ticker": p["ticker"],
                "Sector": p["sector"],
                "País": p["country"],
                "Acciones": round(p["quantity"], 4),
                "Cost / und": round(p["cost_basis_per_share_native"], 4),
                "Precio": round(p["current_price_native"], 4),
                "Valor (EUR)": round(p["current_value_eur"], 2),
                "% NAV": round(p["weight_pct"], 2),
                "P&L %": round(p["unrealized_pnl_pct"], 2),
                "P&L EUR": round(p["unrealized_pnl_eur"], 2),
                "Debate": p["debate_verdict"].replace("_", " "),
            }
            for p in filtered
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        "Para drill-down de un ticker: abre Pantalla 3 y selecciónalo en el "
        "selector. Click en columna para ordenar."
    )


# ----------------------------------------------------------------------
# Block C — Composición visual
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### Composición")

if filtered:
    cv1, cv2 = st.columns([3, 2])
    with cv1:
        treemap_df = pd.DataFrame(
            [
                {
                    "ticker": p["ticker"],
                    "sector": p["sector"],
                    "weight_pct": p["weight_pct"],
                    "pnl_pct": p["unrealized_pnl_pct"],
                }
                for p in filtered
            ]
        )
        fig = px.treemap(
            treemap_df,
            path=[px.Constant("Cartera"), "sector", "ticker"],
            values="weight_pct",
            color="pnl_pct",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
        )
        fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=420)
        st.plotly_chart(fig, use_container_width=True)
    with cv2:
        top10 = sorted(filtered, key=lambda p: -p["weight_pct"])[:10]
        bar_df = pd.DataFrame(
            [{"ticker": p["ticker"], "weight_pct": p["weight_pct"]} for p in top10]
        )
        fig2 = px.bar(
            bar_df,
            x="weight_pct",
            y="ticker",
            orientation="h",
            text="weight_pct",
            labels={"weight_pct": "% NAV", "ticker": ""},
        )
        fig2.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig2.update_layout(
            yaxis={"categoryorder": "total ascending"},
            margin=dict(t=10, l=0, r=20, b=0),
            height=420,
        )
        st.plotly_chart(fig2, use_container_width=True)


# ----------------------------------------------------------------------
# Block D — Concentration analysis
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### Concentraciones")

caps = concentrations["caps"]
if concentrations["breaches"]:
    st.error(
        "Breaches detectados: " + " · ".join(concentrations["breaches"])
    )
else:
    st.success("Sin breaches estructurales en este momento.")

cc1, cc2, cc3 = st.columns(3)


def _row(name: str, weight: float, status: str) -> str:
    color = {"breach": "red", "warn": "yellow", "ok": "green"}.get(status, "neutral")
    return (
        f"<div style='display:flex; justify-content:space-between; "
        f"padding:8px 0; border-bottom:1px solid #1C2333;'>"
        f"<span style='color:#94A0B8;'>{name}</span>"
        f"<span>{status_badge(f'{weight:.1f}%', color)}</span></div>"
    )


with cc1:
    st.markdown(f"**Top single-name** (cap {caps['single']:.0f}%)")
    body = "".join(
        _row(r["ticker"], r["weight_pct"], r["status"])
        for r in concentrations["single_name"]
    )
    st.markdown(
        f"<div class='institutional-card'>{body or 'Sin posiciones.'}</div>",
        unsafe_allow_html=True,
    )

with cc2:
    st.markdown(f"**Sector** (cap {caps['sector']:.0f}%)")
    body = "".join(
        _row(r["sector"], r["weight_pct"], r["status"])
        for r in concentrations["by_sector"]
    )
    st.markdown(
        f"<div class='institutional-card'>{body or 'Sin sectores.'}</div>",
        unsafe_allow_html=True,
    )

with cc3:
    st.markdown(f"**País** (cap {caps['country']:.0f}%)")
    body = "".join(
        _row(r["country"], r["weight_pct"], r["status"])
        for r in concentrations["by_country"]
    )
    st.markdown(
        f"<div class='institutional-card'>{body or 'Sin países.'}</div>",
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------
# Block E — Bulk actions
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### Acciones de cartera")
st.caption(
    "Estas acciones NUNCA ejecutan trades reales en Lightyear. Sólo "
    "actualizan el estado interno del laboratorio."
)

ba1, ba2, ba3 = st.columns(3)


def _run_subprocess(cmd: list[str], spinner_msg: str, success_msg: str) -> None:
    with st.spinner(spinner_msg):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
                timeout=600,
            )
            if result.returncode == 0:
                st.success(success_msg)
            else:
                st.error(
                    (result.stderr or result.stdout or "")[-300:]
                    or "Error desconocido"
                )
        except subprocess.TimeoutExpired:
            st.error("Timeout. Revisa logs/")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error: {exc}")


with ba1:
    if st.button(
        "Reconciliar con Lightyear",
        use_container_width=True,
        help="Abre Pantalla 7 — Operaciones para registro manual.",
    ):
        st.switch_page("pages/7_Trades.py")

with ba2:
    if st.button(
        "Refrescar precios",
        use_container_width=True,
        help="Llama a yfinance para regenerar el snapshot real.",
    ):
        # We use the cerebro generator because it triggers the snapshot
        # rebuilder + technicals + fundamentals refresh in one shot.
        _run_subprocess(
            [sys.executable, "scripts/generate_cerebro_state.py"],
            "Refrescando precios y métricas (60-90s)…",
            "Precios + cerebro actualizados.",
        )

with ba3:
    if st.button(
        "Regenerar cerebro state",
        use_container_width=True,
        help="Re-ejecuta scripts/generate_cerebro_state.py",
    ):
        _run_subprocess(
            [sys.executable, "scripts/generate_cerebro_state.py"],
            "Regenerando cerebro state (60-90s)…",
            "Cerebro state regenerado.",
        )

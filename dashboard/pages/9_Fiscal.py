"""Pantalla 9 — Fiscal LIRPF (España).

Read-only. Derives every metric from data/events/portfolios/real/trades.jsonl
+ the latest snapshot. NEVER computes withholdings to actually file with
AEAT — the IRPF estimate is illustrative; real liquidation depends on
the user's full annual savings base.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from services.fiscal_reader import FiscalReader  # noqa: E402
from styles import format_currency_eur, inject_css, status_badge  # noqa: E402


st.set_page_config(
    page_title="Fiscal LIRPF",
    page_icon=":receipt:",
    layout="wide",
)
inject_css()

if not check_auth():
    st.stop()

reader = FiscalReader()
year_now = date.today().year

st.markdown(
    "<h1 style='margin-bottom:0;'>Fiscal LIRPF</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#64748B; margin-top:4px; font-size:0.9375rem;'>"
    "Tracking fiscal del portfolio real (España). Read-only.</p>",
    unsafe_allow_html=True,
)

st.warning(
    "Las cifras IRPF son estimaciones por tramos de la base del ahorro 2026. "
    "Para liquidación real considera tu base anual completa y consulta "
    "asesor / Modelo 100.",
    icon="ℹ️",
)


# ----------------------------------------------------------------------
# Block A — Year summary
# ----------------------------------------------------------------------
st.markdown(f"### A. Resumen fiscal {year_now}")

selected_year = st.selectbox(
    "Año fiscal",
    options=[year_now, year_now - 1, year_now - 2, year_now - 3],
    index=0,
)
breakdown = reader.get_realized_pnl_breakdown(selected_year)
prev = reader.get_realized_pnl_breakdown(selected_year - 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Ganancias realizadas",
    format_currency_eur(breakdown["gains_eur"], 2),
    f"{breakdown['n_gains']} ventas",
)
c2.metric(
    "Pérdidas realizadas",
    format_currency_eur(breakdown["losses_eur"], 2),
    f"{breakdown['n_losses']} ventas",
)
delta_net = breakdown["net_eur"] - prev["net_eur"]
c3.metric(
    "Neto",
    format_currency_eur(breakdown["net_eur"], 2),
    f"{delta_net:+.2f} EUR vs {selected_year - 1}",
)
c4.metric(
    "IRPF estimado",
    format_currency_eur(breakdown["estimated_irpf_eur"], 2),
    "base ahorro 2026",
)

if breakdown["loss_carryforward_available_eur"] < 0:
    st.info(
        f"Pérdidas compensables próximos "
        f"{breakdown['loss_carryforward_horizon_years']} años: "
        f"{format_currency_eur(breakdown['loss_carryforward_available_eur'], 2)}"
        " (LIRPF art. 49)."
    )


# ----------------------------------------------------------------------
# Block B — 2-month rule alerts
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### B. Regla de 2 meses (LIRPF art. 33.5 f)")

st.caption(
    "Si vendes con pérdida y recompras el mismo ISIN dentro de 2 meses, "
    "la pérdida se difiere hasta que vendas las nuevas acciones."
)

locks = reader.get_active_two_month_locks()
if not locks:
    st.success("Sin restricciones activas hoy.")
else:
    rows = []
    for lock in locks:
        rows.append(
            {
                "Ticker": lock["ticker"],
                "Fecha venta": lock["sale_date"],
                "Pérdida (EUR)": lock["loss_eur"],
                "Recompra detectada": "sí" if lock["repurchase_detected"] else "no",
                "Hasta": lock["window_end"],
                "Días restantes": lock.get("days_remaining"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    for lock in locks:
        if lock["repurchase_detected"]:
            st.error(
                f"{lock['ticker']}: recompra detectada el "
                f"{lock['repurchase_detail']['trade_date']} dentro del "
                "window. La pérdida queda DIFERIDA hasta que vendas las "
                "nuevas acciones."
            )


# ----------------------------------------------------------------------
# Block C — FIFO log + CSV export
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown(f"### C. Log FIFO {selected_year}")

fifo = reader.get_fifo_log(selected_year)
if not fifo:
    st.caption(f"Sin ventas registradas en {selected_year}.")
else:
    fifo_df = pd.DataFrame(
        [
            {
                "Fecha venta": r["sale_date"],
                "Ticker": r["ticker"],
                "ISIN": r["isin"],
                "Acciones": r["shares"],
                "Coste base lote (EUR)": r["cost_basis_eur_lot"],
                "Precio venta": r["sale_price_native"],
                "Ingreso (EUR)": r["proceeds_eur"],
                "P&L lote (EUR)": r["realized_pnl_eur_lot"],
                "Pérdida": "sí" if r["is_loss"] else "no",
                "Lot ID": r["lot_id"],
            }
            for r in fifo
        ]
    )
    st.dataframe(fifo_df, use_container_width=True, hide_index=True)
    csv_bytes = reader.export_fifo_csv(selected_year).encode("utf-8")
    st.download_button(
        "Exportar CSV (gestor / Modelo 100)",
        data=csv_bytes,
        file_name=f"fifo_log_{selected_year}.csv",
        mime="text/csv",
    )


# ----------------------------------------------------------------------
# Block D — Q4 tax-loss harvesting candidates
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### D. Pre-año (Q4): tax-loss harvesting")

candidates = reader.get_tax_loss_harvesting_candidates()
if date.today().month < 10:
    st.caption(
        "Esta sección sólo se activa entre octubre y diciembre, cuando "
        "tiene sentido planificar el cierre fiscal."
    )
elif not candidates:
    st.success("Sin candidatos: ninguna posición con pérdida latente >5%.")
else:
    st.info(
        f"{len(candidates)} candidatos a tax-loss harvesting. "
        "Vender antes del 31-dic permite aplicar la pérdida contra ganancias del año."
    )
    for c in candidates:
        badge = status_badge(
            f"{c['unrealized_pnl_pct']:.1f}%", "yellow"
        )
        st.markdown(
            f"""
            <div class="institutional-card">
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:6px;">
                    <span style="font-family:'JetBrains Mono', monospace;
                                font-weight:600;">{c['ticker']}</span>
                    {badge}
                    <span style="font-size:0.75rem; color:#64748B;">
                        valor {format_currency_eur(c['current_value_eur'], 0)}
                    </span>
                </div>
                <p style="margin:0; color:#475569; font-size:0.9rem;">{c['reasoning']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

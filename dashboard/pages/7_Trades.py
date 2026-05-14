"""Pantalla 7 — Registro de operaciones (manual ingest only).

Phase 2D-extended scope. Four blocks:

  A — Estado de sincronización (snapshot, último trade, deriva).
  B — Registro manual (form único: ticker, side, qty, price, currency,
      fees, FX, fecha, notas).
  C — Preview + compliance + confirmación (cap 12% single-name, cash o
      shares suficientes, 2-month rule LIRPF si BUY).
  D — Histórico filtrado (últimos N trades + filtros básicos).

Out of scope on purpose (deferred until real Lightyear sample available):
  - Tab "Subir CSV Lightyear"
  - Tab "Acción rápida" (LLM parsing de texto libre)
  - Bloque E — Reconciliación NAV automatizada
  - Bloque F — Otras acciones (depósito, dividendo)
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DASHBOARD_ROOT.parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from services.position_reader import PositionReader  # noqa: E402
from styles import (  # noqa: E402
    format_currency_eur,
    format_percent,
    inject_css,
    status_badge,
)

from trade_ingest import (  # type: ignore  # noqa: E402
    build_manual_trade,
    check_compliance,
    compliance_to_dict,
    get_all_trades,
    get_recent_trades,
    persist_trade,
)


st.set_page_config(
    page_title="Operaciones",
    page_icon=":receipt:",
    layout="wide",
)
inject_css()

if not check_auth():
    st.stop()


# ----------------------------------------------------------------------
# Header + caveat
# ----------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0;'>Operaciones</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
    "Registro manual de trades del portfolio real. La carga por CSV de "
    "Lightyear se añadirá cuando dispongamos de un export real.</p>",
    unsafe_allow_html=True,
)

st.info(
    "Carga por CSV de Lightyear: pendiente de un sample real para no "
    "sobre-ajustar el parser. Por ahora solo registro manual.",
    icon="ℹ️",
)


# ----------------------------------------------------------------------
# Block A — Sync status
# ----------------------------------------------------------------------
def _render_sync_status() -> None:
    pr = PositionReader()
    snap = pr.get_latest_snapshot("real")
    all_trades = get_all_trades()
    last_trade = None
    last_trade_date = None
    for ev in reversed(all_trades):
        if ev.get("event_type") == "trade":
            last_trade = ev
            last_trade_date = ev.get("trade_date")
            break

    snap_date = snap.get("as_of_date") if snap else None
    nav = snap.get("nav_total_eur") if snap else None
    cash = snap.get("cash_eur") if snap else None
    pos_count = snap.get("positions_count") if snap else None

    drift_label = "—"
    if snap_date and last_trade_date:
        try:
            drift_days = (
                date.fromisoformat(snap_date)
                - date.fromisoformat(last_trade_date)
            ).days
            if drift_days < 0:
                drift_label = (
                    f"{abs(drift_days)} días — hay trades posteriores al "
                    "snapshot, regenera"
                )
            elif drift_days == 0:
                drift_label = "0 días — alineado"
            else:
                drift_label = f"{drift_days} días"
        except ValueError:
            drift_label = "?"

    st.markdown("### A. Estado de sincronización")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Snapshot", snap_date or "—")
    with c2:
        st.metric("NAV", format_currency_eur(nav, decimals=2))
    with c3:
        st.metric("Cash", format_currency_eur(cash, decimals=2))
    with c4:
        st.metric("Posiciones", pos_count if pos_count is not None else "—")
    c5, c6 = st.columns(2)
    with c5:
        st.metric("Último trade", last_trade_date or "—")
    with c6:
        st.metric("Deriva snapshot ↔ trade", drift_label)


_render_sync_status()
st.divider()


# ----------------------------------------------------------------------
# Block B — Manual entry form
# ----------------------------------------------------------------------
st.markdown("### B. Registrar operación manual")
st.caption(
    "Una operación = una línea en `data/events/portfolios/real/trades.jsonl`. "
    "El compliance se evalúa antes de persistir. La operación nunca se "
    "ejecuta en Lightyear: tú la has hecho manualmente y aquí solo se "
    "espeja para auditoría."
)

with st.form("manual_trade_form", clear_on_submit=False):
    cA, cB = st.columns(2)
    with cA:
        side = st.selectbox(
            "Tipo",
            options=["buy", "sell"],
            format_func=lambda s: "Compra" if s == "buy" else "Venta",
            key="form_side",
        )
        ticker = st.text_input("Ticker", value="", key="form_ticker").upper()
        isin = st.text_input("ISIN", value="", key="form_isin").upper()
        exchange = st.text_input(
            "Mercado (NASDAQ/NYSE/...)", value="NASDAQ", key="form_exchange"
        ).upper()
        currency = st.selectbox(
            "Divisa",
            options=["USD", "EUR", "GBP"],
            index=0,
            key="form_currency",
        )
    with cB:
        quantity = st.number_input(
            "Cantidad de acciones",
            min_value=0.0,
            value=0.0,
            step=0.0001,
            format="%.6f",
            key="form_qty",
        )
        price_native = st.number_input(
            "Precio por acción (en divisa nativa)",
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.4f",
            key="form_price",
        )
        fees_native = st.number_input(
            "Comisiones + half-spread + FX fee (nativo)",
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.4f",
            key="form_fees",
        )
        fx_rate = st.number_input(
            "FX (USD por EUR — Lightyear te la reporta)",
            min_value=0.0001,
            value=1.1738,
            step=0.0001,
            format="%.4f",
            key="form_fx",
        )
        trade_date = st.date_input(
            "Fecha de la operación",
            value=date.today(),
            key="form_date",
        )

    notes = st.text_area(
        "Notas (intent, contexto, link a tesis si aplica)",
        value="",
        key="form_notes",
        height=80,
    )

    submitted = st.form_submit_button("Construir preview")

if submitted:
    if not ticker or not isin or quantity <= 0 or price_native <= 0:
        st.error(
            "Faltan campos obligatorios: ticker, ISIN, cantidad, precio."
        )
    else:
        try:
            trade = build_manual_trade(
                side=side,
                trade_date=trade_date.isoformat(),
                ticker=ticker,
                isin=isin,
                exchange=exchange or "UNKNOWN",
                currency=currency,
                quantity=float(quantity),
                price_native=float(price_native),
                fees_native=float(fees_native),
                fx_rate_usd_per_eur=float(fx_rate),
                notes=notes,
            )
            st.session_state["pending_trade"] = trade
        except ValueError as exc:
            st.error(f"Error en los datos: {exc}")


# ----------------------------------------------------------------------
# Block C — Preview + compliance + confirm
# ----------------------------------------------------------------------
pending = st.session_state.get("pending_trade")
if pending is not None:
    st.divider()
    st.markdown("### C. Preview y compliance")

    # Preview table
    icon = "🟢" if pending.side == "buy" else "🔴"
    side_label = "COMPRA" if pending.side == "buy" else "VENTA"
    st.markdown(
        f"#### {icon} {side_label} · {pending.quantity} {pending.ticker} "
        f"@ {pending.price_native:.4f} {pending.currency}"
    )

    cP1, cP2, cP3 = st.columns(3)
    with cP1:
        st.metric(
            "Bruto (nativo)",
            f"{pending.gross_value_native:,.2f} {pending.currency}",
        )
        st.metric("Bruto (EUR)", format_currency_eur(pending.gross_value_eur, 2))
    with cP2:
        st.metric(
            "Fees (nativo)",
            f"{pending.fees_native:,.2f} {pending.currency}",
        )
        st.metric("Fees (EUR)", format_currency_eur(pending.fees_eur, 2))
    with cP3:
        net_label = "Coste neto" if pending.side == "buy" else "Importe neto"
        st.metric(
            f"{net_label} (nativo)",
            f"{pending.net_value_native:,.2f} {pending.currency}",
        )
        st.metric(
            f"{net_label} (EUR)",
            format_currency_eur(pending.net_value_eur, 2),
        )

    st.caption(
        f"Fecha: {pending.trade_date} · ISIN: {pending.isin} · "
        f"Mercado: {pending.exchange} · FX: {pending.fx_rate_usd_per_eur:.4f}"
    )
    if pending.notes:
        with st.expander("Notas", expanded=False):
            st.text(pending.notes)

    # Compliance
    payload = check_compliance(pending, as_of_date=date.today())
    payload_dict = compliance_to_dict(payload)

    st.markdown("#### Compliance")
    if payload.blocked:
        st.error(
            "OPERACIÓN BLOQUEADA: hay al menos un check con severidad `block`. "
            "Ajusta los datos o cancela el preview."
        )
    else:
        st.success(
            "Compliance OK. Puedes confirmar la operación."
        )

    for finding in payload_dict["findings"]:
        sev = finding["severity"]
        color_map = {"block": "red", "warn": "yellow", "info": "green"}
        badge = status_badge(
            sev.upper(), color_map.get(sev, "neutral")
        )
        st.markdown(
            f"{badge} **{finding['code']}** — {finding['message']}",
            unsafe_allow_html=True,
        )

    if payload.post_trade_weight_pct is not None:
        st.caption(
            f"Peso post-trade estimado: "
            f"{format_percent(payload.post_trade_weight_pct, 2)}"
        )
    if payload.post_trade_cash_eur is not None:
        st.caption(
            f"Cash post-trade estimado: "
            f"{format_currency_eur(payload.post_trade_cash_eur, 2)}"
        )
    if payload.post_trade_position_qty is not None:
        st.caption(
            f"Cantidad post-trade estimada: "
            f"{payload.post_trade_position_qty}"
        )

    cC1, cC2 = st.columns(2)
    with cC1:
        confirm_disabled = payload.blocked
        if st.button(
            "Confirmar y persistir",
            type="primary",
            disabled=confirm_disabled,
            key="confirm_persist",
        ):
            event_id = persist_trade(pending, as_of_date=date.today())
            st.success(
                f"Trade persistido. event_id: `{event_id}`. "
                "Recuerda regenerar el snapshot real si quieres ver el "
                "efecto en Pantalla 1 (`python scripts/generate_cerebro_state.py`)."
            )
            st.session_state.pop("pending_trade", None)
            st.rerun()
    with cC2:
        if st.button("Descartar preview", key="discard_preview"):
            st.session_state.pop("pending_trade", None)
            st.rerun()


# ----------------------------------------------------------------------
# Block D — Histórico filtrado
# ----------------------------------------------------------------------
st.divider()
st.markdown("### D. Histórico de operaciones")

all_trades = [
    ev for ev in get_all_trades() if ev.get("event_type") == "trade"
]
if not all_trades:
    st.info("Aún no hay trades registrados.")
else:
    cF1, cF2, cF3 = st.columns(3)
    with cF1:
        ticker_filter = st.text_input(
            "Filtrar por ticker (vacío = todos)", value="", key="hist_ticker"
        ).upper().strip()
    with cF2:
        side_filter = st.selectbox(
            "Side",
            options=["(todos)", "buy", "sell"],
            key="hist_side",
        )
    with cF3:
        days_window = st.number_input(
            "Últimos N días",
            min_value=1,
            max_value=3650,
            value=90,
            step=1,
            key="hist_days",
        )

    filtered = []
    cutoff = date.today().toordinal() - int(days_window)
    for ev in all_trades:
        td_str = ev.get("trade_date")
        if isinstance(td_str, str):
            try:
                if date.fromisoformat(td_str).toordinal() < cutoff:
                    continue
            except ValueError:
                continue
        if ticker_filter and ev.get("ticker") != ticker_filter:
            continue
        if side_filter != "(todos)" and ev.get("side") != side_filter:
            continue
        filtered.append(ev)

    rows = []
    for ev in reversed(filtered):
        rows.append(
            {
                "fecha": ev.get("trade_date", "—"),
                "side": ev.get("side", "—"),
                "ticker": ev.get("ticker", "—"),
                "qty": ev.get("quantity", 0),
                "precio": ev.get("price_native", 0),
                "ccy": ev.get("currency", "—"),
                "neto_eur": (
                    ev.get("net_outflow_eur")
                    or ev.get("proceeds_eur")
                    or ev.get("gross_value_eur")
                    or 0
                ),
                "pnl_eur": ev.get("realized_pnl_eur"),
                "ingest": ev.get(
                    "ingest_source",
                    "legacy_event" if "user_executed" in ev else "—",
                ),
                "event_id": ev.get("event_id", "—"),
            }
        )
    st.caption(
        f"Mostrando {len(rows)} trades (de {len(all_trades)} totales)."
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)

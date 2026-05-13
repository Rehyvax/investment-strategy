"""Pantalla 3 — Detalle de Posición.

Drill-down view per ticker. Seven blocks (A–G):
- A: Header con bottom-line (action badge) + posición + P&L.
- B: Tesis vigente + falsifiers visuales.
- B': Histórico de tesis (timeline).
- C: Opinión LLM matizada (cache por sesión).
- D: Datos clave compactos.
- E: Noticias placeholder (Fase 3 news-scanner).
- F: Eventos próximos — DINÁMICOS desde el cerebro state
     (`upcoming_events_by_asset`), nunca hardcoded.
- G: Acciones (registrar trade, preguntar al cerebro, ver tesis).
"""

from __future__ import annotations

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

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from services.cerebro_state import load_cerebro_state  # noqa: E402
from services.position_reader import PositionReader  # noqa: E402
from services.thesis_reader import ThesisReader  # noqa: E402
from styles import inject_css, status_badge  # noqa: E402

try:
    from llm_narratives import (  # type: ignore  # noqa: E402
        generate_position_opinion,
        is_llm_available,
    )
except ImportError:

    def generate_position_opinion(*args, **kwargs):  # type: ignore
        return None

    def is_llm_available() -> bool:  # type: ignore
        return False


try:
    from llm_chat import chat_about_recommendation, load_env_for_chat  # type: ignore  # noqa: E402

    load_env_for_chat()
except ImportError:

    def chat_about_recommendation(*args, **kwargs):  # type: ignore
        return None


st.set_page_config(
    page_title="Detalle Posición",
    page_icon=":mag:",
    layout="wide",
)

inject_css()

if not check_auth():
    st.stop()

thesis_reader = ThesisReader()
position_reader = PositionReader()

held_assets = position_reader.list_assets("real") or []
thesis_assets = thesis_reader.list_assets()
all_assets = list(dict.fromkeys(held_assets + thesis_assets))

if not all_assets:
    st.error(
        "Sin posiciones ni tesis disponibles. Verifica que existen "
        "snapshots y eventos de tesis."
    )
    st.stop()

st.markdown(
    "<h1 style='margin-bottom:0;'>Detalle de Posición</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#64748B; margin-top:4px; font-size:0.9375rem;'>"
    "Vista drill-down por ticker — tesis vigente, falsifiers, opinión, "
    "eventos próximos.</p>",
    unsafe_allow_html=True,
)

default_asset = st.query_params.get("asset", all_assets[0])
if default_asset not in all_assets:
    default_asset = all_assets[0]

selected = st.selectbox(
    "Selecciona ticker:",
    options=all_assets,
    index=all_assets.index(default_asset),
    key="asset_selector",
)
if selected != default_asset:
    st.query_params["asset"] = selected

position = position_reader.get_position(selected, "real")
all_thesis_versions = thesis_reader.get_all_versions(selected)
authoritative_thesis = thesis_reader.get_authoritative_version(selected)
latest_thesis = thesis_reader.get_latest_thesis_only(selected)


# ----------------------------------------------------------------------
# Block A — Header
# ----------------------------------------------------------------------
def _action_for_header(thesis: dict | None) -> tuple[str, str]:
    if thesis is None:
        return "SIN TESIS", "neutral"
    if thesis.get("event_type") == "thesis_user_override_annotation":
        return "OVERRIDE ACTIVO", "orange"
    rec = (thesis.get("recommendation") or thesis.get("recommendation_v2") or "").lower()
    mapping = {
        "exit": ("SISTEMA RECOMIENDA SALIR", "red"),
        "sell": ("VENDER", "red"),
        "reduce": ("REDUCIR", "orange"),
        "watch": ("VIGILAR", "yellow"),
        "hold": ("MANTENER", "yellow"),
        "buy": ("COMPRAR", "green"),
        "buy_more": ("AUMENTAR", "green"),
        "add": ("AÑADIR", "green"),
    }
    return mapping.get(rec, ("MANTENER", "yellow"))


action_label, action_color = _action_for_header(authoritative_thesis)
action_badge = status_badge(action_label, action_color)

if position:
    cost_basis_eur = float(position.get("cost_basis_eur", 0.0) or 0.0)
    current_value = float(position.get("current_value_eur", 0.0) or 0.0)
    pnl_eur = float(position.get("unrealized_pnl_eur", 0.0) or 0.0)
    pnl_pct = (pnl_eur / cost_basis_eur * 100.0) if cost_basis_eur else 0.0
    if pnl_eur > 0:
        pnl_color = "#15803D"
    elif pnl_eur < 0:
        pnl_color = "#B91C1C"
    else:
        pnl_color = "#64748B"
    weight_pct = float(position.get("weight_pct", 0.0) or 0.0)
    quantity = float(position.get("quantity", 0.0) or 0.0)
    currency = position.get("currency", "USD")

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
                <div>
                    <h2 style="margin:0 0 4px 0; color:#0F172A; font-size:1.5rem; font-weight:700; font-family:'JetBrains Mono', monospace;">{selected}</h2>
                    <div style="display:flex; align-items:center; gap:8px;">{action_badge}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.75rem; color:#64748B; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">Posición actual</div>
                    <div style="font-family:'JetBrains Mono', monospace; font-size:1.25rem; color:#0F172A; font-weight:600;">EUR {int(current_value):,}</div>
                    <div style="font-size:0.875rem; color:#64748B;">{weight_pct:.2f}% NAV · {quantity:.4f} und.</div>
                </div>
            </div>
            <div style="margin-top:16px; padding-top:16px; border-top:1px solid #E2E8F0; display:flex; gap:24px; flex-wrap:wrap;">
                <div>
                    <div style="font-size:0.75rem; color:#64748B; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">Cost basis</div>
                    <div style="font-family:'JetBrains Mono', monospace; color:#475569;">EUR {int(cost_basis_eur):,}</div>
                </div>
                <div>
                    <div style="font-size:0.75rem; color:#64748B; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">P&amp;L latente</div>
                    <div style="font-family:'JetBrains Mono', monospace; color:{pnl_color}; font-weight:600;">{pnl_eur:+.0f} EUR ({pnl_pct:+.2f}%)</div>
                </div>
                <div>
                    <div style="font-size:0.75rem; color:#64748B; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">Currency</div>
                    <div style="font-family:'JetBrains Mono', monospace; color:#475569;">{currency}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.warning(f"No posees {selected} en la cartera actual; sólo hay tesis disponible.")

# ----------------------------------------------------------------------
# Block B — Tesis vigente + falsifiers
# ----------------------------------------------------------------------
st.markdown("<h2>Tesis Vigente</h2>", unsafe_allow_html=True)

if authoritative_thesis:
    version_label = ThesisReader.thesis_version_label(authoritative_thesis)
    ts = authoritative_thesis.get("ts", "")[:10]
    summary = ThesisReader.thesis_summary_text(authoritative_thesis)
    rec = (
        authoritative_thesis.get("recommendation")
        or authoritative_thesis.get("recommendation_v2")
        or ""
    )
    rec_color = {
        "exit": "red",
        "sell": "red",
        "reduce": "orange",
        "watch": "yellow",
        "hold": "yellow",
        "buy": "green",
        "buy_more": "green",
        "add": "green",
    }.get(rec.lower(), "neutral")
    rec_badge = status_badge(
        rec.upper() if rec else "SIN RECOMENDACIÓN", rec_color
    )

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px; flex-wrap:wrap;">
                <span style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#0F172A;">{version_label}</span>
                {rec_badge}
                <span style="font-size:0.75rem; color:#64748B;">{ts}</span>
            </div>
            <p style="color:#475569; line-height:1.6; margin:0; font-size:0.9375rem; white-space:pre-wrap;">{summary[:1500]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    falsifiers = thesis_reader.get_falsifier_status(
        latest_thesis or authoritative_thesis
    )
    if falsifiers:
        st.markdown(
            "<div style='margin-top:16px;'><span style='font-size:0.75rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;'>Falsifiers</span></div>",
            unsafe_allow_html=True,
        )
        for f in falsifiers:
            status = (f.get("status") or "unknown").lower()
            color = {
                "inactive": "#15803D",
                "halfway_activated": "#A16207",
                "activated": "#B91C1C",
                "active": "#B91C1C",
            }.get(status, "#64748B")
            icon = {
                "inactive": "OK",
                "halfway_activated": "1/2",
                "activated": "X",
                "active": "X",
            }.get(status, "?")
            current_block = (
                f"<div style='font-size:0.875rem; color:#64748B; margin-top:4px;'>Actual: {f['current']}</div>"
                if f.get("current")
                else ""
            )
            note_block = (
                f"<div style='font-size:0.8125rem; color:#475569; margin-top:6px; line-height:1.5;'>{f['note'][:240]}</div>"
                if f.get("note")
                else ""
            )
            st.markdown(
                f"""
                <div style="background:#F8FAFC; padding:10px 14px; border-radius:6px; margin-bottom:6px; border-left:3px solid {color};">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="color:{color}; font-size:0.875rem; font-weight:700; min-width:32px; text-align:center;">{icon}</span>
                        <div style="flex:1;">
                            <div style="color:#0F172A; font-weight:500; font-size:0.9375rem;">{f.get('name', '?')}</div>
                            <div style="color:#64748B; font-size:0.8125rem;">Threshold: {f.get('threshold', '—')} · Status: {status}</div>
                            {current_block}
                            {note_block}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
else:
    st.info(f"Sin tesis formal disponible para {selected}.")

# ----------------------------------------------------------------------
# Block B' — Histórico de tesis
# ----------------------------------------------------------------------
if len(all_thesis_versions) > 1:
    st.markdown("<h2>Histórico de Tesis</h2>", unsafe_allow_html=True)
    rows: list[str] = []
    for i, v in enumerate(reversed(all_thesis_versions)):
        is_latest = i == 0
        ts = v.get("ts", "")[:10]
        et = v.get("event_type", "thesis")
        version_label = ThesisReader.thesis_version_label(v)
        rec = (v.get("recommendation") or "").lower()
        if et == "thesis_user_override_annotation":
            descr, bcolor = "Override consciente del usuario", "orange"
        elif rec == "exit":
            descr, bcolor = "Recomendación EXIT", "red"
        elif rec == "reduce":
            descr, bcolor = "Recomendación REDUCE", "orange"
        elif rec == "watch":
            descr, bcolor = "WATCH", "yellow"
        elif rec in ("buy", "buy_more", "add"):
            descr, bcolor = "Recomendación BUY/ADD", "green"
        else:
            descr, bcolor = et.replace("_", " ").title(), "neutral"
        marker_color = "#1E40AF" if is_latest else "#CBD5E1"
        marker_size = "12px" if is_latest else "8px"
        rows.append(
            f"""
            <div style="display:flex; gap:16px; padding:12px 0; border-bottom:1px solid #F1F5F9;">
                <div style="display:flex; flex-direction:column; align-items:center; padding-top:4px;">
                    <div style="width:{marker_size}; height:{marker_size}; border-radius:50%; background:{marker_color};"></div>
                </div>
                <div style="flex:1;">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <span style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#0F172A;">{version_label}</span>
                        {status_badge(descr, bcolor)}
                        <span style="font-size:0.75rem; color:#64748B;">{ts}</span>
                    </div>
                </div>
            </div>
            """
        )
    st.markdown(
        '<div class="institutional-card">' + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------
# Block C — Opinión LLM matizada (session-cached)
# ----------------------------------------------------------------------
st.markdown("<h2>Opinión del Cerebro</h2>", unsafe_allow_html=True)

if position and authoritative_thesis:
    falsifiers = thesis_reader.get_falsifier_status(
        latest_thesis or authoritative_thesis
    )
    if authoritative_thesis.get("event_type") == "thesis_user_override_annotation":
        additional = (
            "Override consciente activo. Usuario eligió HOLD contra la "
            "recomendación EXIT del sistema. "
            + (authoritative_thesis.get("note", "") or "")[:300]
        )
    else:
        additional = (
            authoritative_thesis.get("confidence_justification", "")[:300]
        )

    cache_key = (
        f"opinion_{selected}_"
        f"{authoritative_thesis.get('ts', '')[:10]}_"
        f"{int(position.get('current_value_eur', 0) or 0)}"
    )
    if cache_key not in st.session_state:
        if is_llm_available():
            with st.spinner("Generando opinión…"):
                st.session_state[cache_key] = generate_position_opinion(
                    position,
                    latest_thesis or authoritative_thesis,
                    falsifiers,
                    additional,
                )
        else:
            st.session_state[cache_key] = None

    opinion = st.session_state.get(cache_key)
    if opinion:
        st.markdown(
            f"""
            <div class="institutional-card" style="border-left: 3px solid #1E40AF;">
                <div style="margin-bottom:10px;">
                    {status_badge("LLM", "blue")}
                </div>
                <p style="color:#0F172A; line-height:1.7; margin:0; font-size:0.9375rem; white-space:pre-wrap;">{opinion}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        rule_text = (
            "Posición mantenida con override consciente. Próximo gate "
            "decisivo en earnings."
            if authoritative_thesis.get("event_type") == "thesis_user_override_annotation"
            else "Tesis activa. Monitor de falsifiers automático."
        )
        st.markdown(
            f"""
            <div class="institutional-card" style="border-left: 3px solid #64748B;">
                <div style="margin-bottom:10px;">{status_badge("DETERMINISTA", "neutral")}</div>
                <p style="color:#475569; line-height:1.7; margin:0; font-size:0.9375rem;">{rule_text}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.info("Sin opinión: se necesita posición + tesis.")

# ----------------------------------------------------------------------
# Block D — Datos clave
# ----------------------------------------------------------------------
st.markdown("<h2>Datos Clave</h2>", unsafe_allow_html=True)
if position:
    quantity = float(position.get("quantity", 0.0) or 0.0)
    cost_basis_native = float(position.get("cost_basis_native", 0.0) or 0.0)
    cb_per_unit = cost_basis_native / quantity if quantity > 0 else 0.0
    current_price = float(position.get("current_price_native", 0.0) or 0.0)
    weight_pct = float(position.get("weight_pct", 0.0) or 0.0)
    currency = position.get("currency", "USD")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Precio actual", f"{current_price:.2f} {currency}")
    c2.metric("Cost basis / und", f"{cb_per_unit:.2f} {currency}")
    c3.metric("Unidades", f"{quantity:.4f}")
    c4.metric("% NAV", f"{weight_pct:.2f}%")
    st.caption(
        "Fundamentals (P/E, ROIC, márgenes, FCF) requieren integración "
        "fundamental-analyst en Fase 3."
    )
else:
    st.caption(f"Sin posición activa de {selected}.")

# ----------------------------------------------------------------------
# Block E — Noticias placeholder
# ----------------------------------------------------------------------
st.markdown("<h2>Noticias Relevantes</h2>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="institutional-card" style="background:#F8FAFC;">
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
            {status_badge("PENDIENTE", "neutral")}
            <span style="font-size:0.75rem; color:#64748B; text-transform:uppercase; letter-spacing:0.05em;">News-scanner integration en Fase 3</span>
        </div>
        <p style="margin:0; color:#475569; line-height:1.6; font-size:0.9375rem;">
        News-scanner automático para {selected} pendiente de integración.
        Filtrará últimos 7 días por relevancia material.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Block F — Eventos próximos (DINÁMICOS desde cerebro state)
# ----------------------------------------------------------------------
st.markdown("<h2>Eventos Próximos</h2>", unsafe_allow_html=True)

try:
    cerebro_state = load_cerebro_state()
except Exception:
    cerebro_state = {}

cerebro_events_by_asset = cerebro_state.get("upcoming_events_by_asset", {}) or {}
events = cerebro_events_by_asset.get(selected, [])

if events:
    rows: list[str] = []
    for evt in events:
        source_raw = evt.get("source", "")
        source_label = (
            source_raw.replace("_", " ").title() if source_raw else ""
        )
        source_badge = (
            f"<span style='font-size:0.6875rem; color:#94A3B8; margin-left:8px;'>[{source_label}]</span>"
            if source_label
            else ""
        )
        rows.append(
            f"""
            <div style="display:flex; gap:16px; padding:10px 0; border-bottom:1px solid #F1F5F9;">
                <div style="font-family:'JetBrains Mono', monospace; color:#1E40AF; font-weight:600; min-width:110px;">{evt.get('date', '—')}</div>
                <div style="color:#475569; line-height:1.5; flex:1;">{evt.get('event', '—')}{source_badge}</div>
            </div>
            """
        )
    st.markdown(
        '<div class="institutional-card">' + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )
else:
    st.caption(
        f"Sin eventos próximos detectados para {selected} "
        "(fuentes: yfinance + trades + thesis)."
    )

# ----------------------------------------------------------------------
# Block G — Acciones
# ----------------------------------------------------------------------
st.markdown("<h2>Acciones</h2>", unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)

if col1.button(
    "Registrar trade manual",
    use_container_width=True,
    type="secondary",
    help="Pantalla 7 Trades pendiente Fase 3.",
):
    st.info("Pantalla 7 Trades pendiente de implementación.")

ask_clicked = col2.button(
    "Preguntar al cerebro",
    use_container_width=True,
    type="primary",
    help=(
        "Chat ad-hoc sobre esta posición (~0.01–0.02 USD)."
        if is_llm_available()
        else "API key no configurada."
    ),
    disabled=not is_llm_available(),
)
if ask_clicked:
    st.session_state[f"chat_open_detalle_{selected}"] = True

if col3.button(
    "Ver tesis completa",
    use_container_width=True,
    type="secondary",
    help="Pantalla 8 Tesis pendiente Fase 3.",
):
    st.info("Pantalla 8 Tesis pendiente de implementación.")

if st.session_state.get(f"chat_open_detalle_{selected}"):
    with st.expander(f"Preguntar sobre {selected}", expanded=True):
        question = st.text_area(
            "Tu pregunta:",
            placeholder=(
                f"Ejemplo: ¿qué pasa si {selected} cae 10% antes del "
                "próximo earnings?"
            ),
            key=f"q_detalle_{selected}",
            height=80,
        )
        cols = st.columns([1, 4])
        submit = cols[0].button("Enviar", key=f"send_detalle_{selected}", type="primary")
        cols[1].caption("Coste: ~0.01–0.02 USD por pregunta.")

        if submit and question and question.strip():
            opinion_text = st.session_state.get(cache_key, "") if position and authoritative_thesis else ""
            rec_like = {
                "asset": selected,
                "type": action_label,
                "headline": f"Detalle posición {selected}",
                "narrative": (opinion_text or "")[:400],
                "action": "Consulta drill-down",
                "priority": "medium",
            }
            nav_for_chat = float(
                position.get("_nav_total_eur", 50000.0)
                if position
                else 50000.0
            )
            portfolio_ctx = {"nav_total_eur": nav_for_chat}
            with st.spinner("Consultando…"):
                response = chat_about_recommendation(
                    rec_like, question, portfolio_ctx
                )
            if response:
                st.session_state[f"chat_answer_detalle_{selected}"] = response
            else:
                st.session_state[f"chat_answer_detalle_{selected}"] = (
                    "Error al consultar. Verifica la API key."
                )

        answer = st.session_state.get(f"chat_answer_detalle_{selected}")
        if answer:
            st.markdown(
                f"""
                <div class="institutional-card" style="background:#F0F9FF; border-left: 3px solid #1E40AF; margin-top:12px;">
                    <span style="font-size:0.75rem; color:#1E40AF; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Respuesta del cerebro</span>
                    <p style="margin:8px 0 0 0; color:#0F172A; line-height:1.6; font-size:0.9375rem; white-space:pre-wrap;">{answer}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if st.button("Cerrar chat", key=f"close_detalle_{selected}", type="secondary"):
            st.session_state.pop(f"chat_open_detalle_{selected}", None)
            st.session_state.pop(f"chat_answer_detalle_{selected}", None)
            st.rerun()

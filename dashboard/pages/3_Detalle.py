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
    initial_sidebar_state="expanded",
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
    "<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
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
        pnl_color = "#10B981"
    elif pnl_eur < 0:
        pnl_color = "#EF4444"
    else:
        pnl_color = "#94A0B8"
    weight_pct = float(position.get("weight_pct", 0.0) or 0.0)
    quantity = float(position.get("quantity", 0.0) or 0.0)
    currency = position.get("currency", "USD")

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
                <div>
                    <h2 style="margin:0 0 4px 0; color:#E8ECF4; font-size:1.5rem; font-weight:700; font-family:'JetBrains Mono', monospace;">{selected}</h2>
                    <div style="display:flex; align-items:center; gap:8px;">{action_badge}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.75rem; color:#94A0B8; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">Posición actual</div>
                    <div style="font-family:'JetBrains Mono', monospace; font-size:1.25rem; color:#E8ECF4; font-weight:600;">EUR {int(current_value):,}</div>
                    <div style="font-size:0.875rem; color:#94A0B8;">{weight_pct:.2f}% NAV · {quantity:.4f} und.</div>
                </div>
            </div>
            <div style="margin-top:16px; padding-top:16px; border-top:1px solid #2A3142; display:flex; gap:24px; flex-wrap:wrap;">
                <div>
                    <div style="font-size:0.75rem; color:#94A0B8; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">Cost basis</div>
                    <div style="font-family:'JetBrains Mono', monospace; color:#94A0B8;">EUR {int(cost_basis_eur):,}</div>
                </div>
                <div>
                    <div style="font-size:0.75rem; color:#94A0B8; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">P&amp;L latente</div>
                    <div style="font-family:'JetBrains Mono', monospace; color:{pnl_color}; font-weight:600;">{pnl_eur:+.0f} EUR ({pnl_pct:+.2f}%)</div>
                </div>
                <div>
                    <div style="font-size:0.75rem; color:#94A0B8; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">Currency</div>
                    <div style="font-family:'JetBrains Mono', monospace; color:#94A0B8;">{currency}</div>
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
                <span style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#E8ECF4;">{version_label}</span>
                {rec_badge}
                <span style="font-size:0.75rem; color:#94A0B8;">{ts}</span>
            </div>
            <p style="color:#94A0B8; line-height:1.6; margin:0; font-size:0.9375rem; white-space:pre-wrap;">{summary[:1500]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    falsifiers = thesis_reader.get_falsifier_status(
        latest_thesis or authoritative_thesis
    )
    if falsifiers:
        st.markdown(
            "<div style='margin-top:16px;'><span style='font-size:0.75rem; color:#94A0B8; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;'>Falsifiers</span></div>",
            unsafe_allow_html=True,
        )
        for f in falsifiers:
            status = (f.get("status") or "unknown").lower()
            color = {
                "inactive": "#10B981",
                "halfway_activated": "#F59E0B",
                "activated": "#EF4444",
                "active": "#EF4444",
            }.get(status, "#94A0B8")
            icon = {
                "inactive": "OK",
                "halfway_activated": "1/2",
                "activated": "X",
                "active": "X",
            }.get(status, "?")
            current_block = (
                f"<div style='font-size:0.875rem; color:#94A0B8; margin-top:4px;'>Actual: {f['current']}</div>"
                if f.get("current")
                else ""
            )
            note_block = (
                f"<div style='font-size:0.8125rem; color:#94A0B8; margin-top:6px; line-height:1.5;'>{f['note'][:240]}</div>"
                if f.get("note")
                else ""
            )
            st.markdown(
                f"""
                <div style="background:#131825; padding:10px 14px; border-radius:6px; margin-bottom:6px; border-left:3px solid {color};">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="color:{color}; font-size:0.875rem; font-weight:700; min-width:32px; text-align:center;">{icon}</span>
                        <div style="flex:1;">
                            <div style="color:#E8ECF4; font-weight:500; font-size:0.9375rem;">{f.get('name', '?')}</div>
                            <div style="color:#94A0B8; font-size:0.8125rem;">Threshold: {f.get('threshold', '—')} · Status: {status}</div>
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
        marker_color = "#3B82F6" if is_latest else "#3A4258"
        marker_size = "12px" if is_latest else "8px"
        rows.append(
            f"""
            <div style="display:flex; gap:16px; padding:12px 0; border-bottom:1px solid #1C2333;">
                <div style="display:flex; flex-direction:column; align-items:center; padding-top:4px;">
                    <div style="width:{marker_size}; height:{marker_size}; border-radius:50%; background:{marker_color};"></div>
                </div>
                <div style="flex:1;">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <span style="font-family:'JetBrains Mono', monospace; font-weight:600; color:#E8ECF4;">{version_label}</span>
                        {status_badge(descr, bcolor)}
                        <span style="font-size:0.75rem; color:#94A0B8;">{ts}</span>
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
# Block C — Opinión LLM matizada (session-cached, 4 analyst inputs)
# ----------------------------------------------------------------------
st.markdown("<h2>Opinión del Cerebro</h2>", unsafe_allow_html=True)

# Cerebro state used by Bloques C, D, E and F.
try:
    cerebro_state = load_cerebro_state()
except Exception:
    cerebro_state = {}

asset_technicals = (
    cerebro_state.get("technicals_by_asset", {}) or {}
).get(selected, {})
asset_fundamentals = (
    cerebro_state.get("fundamentals_by_asset", {}) or {}
).get(selected, {})
asset_news = (
    cerebro_state.get("news_by_asset", {}) or {}
).get(selected, [])

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

    # Cache key includes a hash of the analyst inputs so that a new
    # cerebro regeneration invalidates the cached opinion automatically.
    inputs_signature = (
        f"t{asset_technicals.get('as_of_date', '')}"
        f"_f{asset_fundamentals.get('as_of_date', '')}"
        f"_n{len(asset_news)}"
    )
    cache_key = (
        f"opinion_{selected}_"
        f"{authoritative_thesis.get('ts', '')[:10]}_"
        f"{int(position.get('current_value_eur', 0) or 0)}_"
        f"{inputs_signature}"
    )
    if cache_key not in st.session_state:
        if is_llm_available():
            with st.spinner("Generando opinión…"):
                st.session_state[cache_key] = generate_position_opinion(
                    position,
                    latest_thesis or authoritative_thesis,
                    falsifiers,
                    additional,
                    technicals=asset_technicals or None,
                    fundamentals=asset_fundamentals or None,
                    news=asset_news or None,
                )
        else:
            st.session_state[cache_key] = None

    opinion = st.session_state.get(cache_key)
    if opinion:
        st.markdown(
            f"""
            <div class="institutional-card" style="border-left: 3px solid #3B82F6;">
                <div style="margin-bottom:10px;">
                    {status_badge("LLM", "blue")}
                </div>
                <p style="color:#E8ECF4; line-height:1.7; margin:0; font-size:0.9375rem; white-space:pre-wrap;">{opinion}</p>
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
            <div class="institutional-card" style="border-left: 3px solid #94A0B8;">
                <div style="margin-bottom:10px;">{status_badge("DETERMINISTA", "neutral")}</div>
                <p style="color:#94A0B8; line-height:1.7; margin:0; font-size:0.9375rem;">{rule_text}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.info("Sin opinión: se necesita posición + tesis.")

# ----------------------------------------------------------------------
# Block H — Debate Bull vs Bear (Fase 3D)
# ----------------------------------------------------------------------
st.markdown("<h2>Debate Bull vs Bear</h2>", unsafe_allow_html=True)

last_debate = (cerebro_state.get("debates_by_asset", {}) or {}).get(selected)

if last_debate:
    verdict = last_debate.get("verdict", "thesis_neutral")
    suggested = last_debate.get("suggested_action", "maintain")
    confidence = last_debate.get("confidence", "low")
    weight = last_debate.get("weight", "balanced")
    timestamp = (last_debate.get("timestamp") or "")[:10]
    reasoning = last_debate.get("reasoning", "")
    trigger = last_debate.get("trigger_reason", "—")
    key_evidence = last_debate.get("key_evidence_for_verdict", "")
    key_trigger = last_debate.get("key_trigger_to_monitor", "")

    verdict_color = {
        "thesis_strengthened": "green",
        "thesis_neutral": "neutral",
        "thesis_weakened": "yellow",
        "thesis_invalidated": "red",
    }.get(verdict, "neutral")
    weight_color = {
        "bull_wins": "green",
        "bear_wins": "red",
        "balanced": "neutral",
    }.get(weight, "neutral")

    verdict_badge = status_badge(
        verdict.upper().replace("_", " "), verdict_color
    )
    weight_badge = status_badge(
        weight.upper().replace("_", " "), weight_color
    )

    extras = ""
    if key_evidence:
        extras += (
            f"<div style='margin-top:8px; font-size:0.8125rem; color:#94A0B8;'>"
            f"<b>Evidencia clave:</b> {key_evidence}</div>"
        )
    if key_trigger:
        extras += (
            f"<div style='margin-top:4px; font-size:0.8125rem; color:#94A0B8;'>"
            f"<b>Trigger a vigilar:</b> {key_trigger}</div>"
        )

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px;">
                {verdict_badge}
                {weight_badge}
                <span style="font-size:0.75rem; color:#94A0B8;">
                    {timestamp} · confianza {confidence} · trigger {trigger}
                </span>
            </div>
            <p style="color:#E8ECF4; line-height:1.6; margin:0 0 10px 0;
                      white-space:pre-wrap;">{reasoning}</p>
            {extras}
            <div style="margin-top:14px; background:#1C2333; padding:12px;
                        border-radius:6px;">
                <span style="font-size:0.75rem; color:#94A0B8; font-weight:600;
                             text-transform:uppercase; letter-spacing:0.05em;">
                    Acción sugerida
                </span>
                <p style="margin:6px 0 0 0; color:#E8ECF4;">{suggested}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    bull_rounds = last_debate.get("bull_rounds") or []
    bear_rounds = last_debate.get("bear_rounds") or []
    if bull_rounds or bear_rounds:
        with st.expander("Ver transcripción del debate"):
            for i in range(max(len(bull_rounds), len(bear_rounds))):
                if i < len(bull_rounds):
                    st.markdown(
                        f"**Bull (round {i + 1}):** {bull_rounds[i]}"
                    )
                if i < len(bear_rounds):
                    st.markdown(
                        f"**Bear (round {i + 1}):** {bear_rounds[i]}"
                    )
                if i < max(len(bull_rounds), len(bear_rounds)) - 1:
                    st.markdown("---")
else:
    st.markdown(
        f"""
        <div class="institutional-card" style="background:#131825;">
            <p style="margin:0; color:#94A0B8;">
                Sin debate registrado para {selected}. Se ejecuta semanalmente
                o cuando hay news high relevance.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "Forzar debate ahora",
        key=f"force_debate_{selected}",
        type="secondary",
        help="Coste estimado ~$0.10-0.15 USD por debate (3-4 LLM calls).",
    ):
        with st.spinner("Ejecutando debate Bull vs Bear (60-90s)…"):
            import subprocess
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "scripts/run_weekly_debates.py",
                        "--force",
                        "--ticker",
                        selected,
                    ],
                    capture_output=True,
                    text=True,
                    cwd=str(PROJECT_ROOT),
                    timeout=180,
                )
                if result.returncode == 0:
                    st.success(
                        "Debate completado. Pulsa 'Iniciar evaluación' "
                        "en el sidebar para refrescar el cerebro."
                    )
                else:
                    st.error(
                        f"Error: {result.stderr[:300] or result.stdout[:300]}"
                    )
            except subprocess.TimeoutExpired:
                st.error("Timeout (180s). Revisa logs/weekly_debates.log.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error: {exc}")

# ----------------------------------------------------------------------
# Block D — Datos clave (position + fundamentals + technicals)
# ----------------------------------------------------------------------
st.markdown("<h2>Datos Clave</h2>", unsafe_allow_html=True)


def _fmt_metric_pct(v: float | int | None) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_metric_num(v: float | int | None, fmt: str = "{:.1f}") -> str:
    if v is None:
        return "N/A"
    try:
        return fmt.format(float(v))
    except (TypeError, ValueError):
        return "N/A"


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
else:
    st.caption(f"Sin posición activa de {selected}.")

# Fundamentals row
if asset_fundamentals:
    st.markdown(
        "<div style='margin-top:18px;'><span style='font-size:0.75rem; "
        "color:#94A0B8; font-weight:600; text-transform:uppercase; "
        "letter-spacing:0.05em;'>Fundamentals (yfinance)</span></div>",
        unsafe_allow_html=True,
    )
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("P/E (trailing)", _fmt_metric_num(asset_fundamentals.get("pe_ratio"), "{:.1f}"))
    f1.metric("P/E (forward)", _fmt_metric_num(asset_fundamentals.get("forward_pe"), "{:.1f}"))
    f2.metric("Op margin", _fmt_metric_pct(asset_fundamentals.get("operating_margin")))
    f2.metric("Revenue growth", _fmt_metric_pct(asset_fundamentals.get("revenue_growth")))
    f3.metric("Debt/Equity", _fmt_metric_num(asset_fundamentals.get("debt_to_equity"), "{:.1f}"))
    f3.metric("Current ratio", _fmt_metric_num(asset_fundamentals.get("current_ratio"), "{:.2f}"))
    target_price = asset_fundamentals.get("target_mean_price")
    target_str = (
        f"${target_price:.2f}" if isinstance(target_price, (int, float))
        else "N/A"
    )
    f4.metric("Analyst target", target_str)
    f4.metric(
        "Consensus", asset_fundamentals.get("recommendation_key", "N/A") or "N/A"
    )

    flags = asset_fundamentals.get("flags") or []
    if flags:
        flag_html = " ".join(
            status_badge(f.upper().replace("_", " "), "yellow") for f in flags
        )
        st.markdown(
            f"<div style='margin-top:10px;'>Red flags: {flag_html}</div>",
            unsafe_allow_html=True,
        )

# Technicals row
if asset_technicals:
    st.markdown(
        "<div style='margin-top:18px;'><span style='font-size:0.75rem; "
        "color:#94A0B8; font-weight:600; text-transform:uppercase; "
        "letter-spacing:0.05em;'>Technicals</span></div>",
        unsafe_allow_html=True,
    )
    t1, t2, t3, t4 = st.columns(4)
    t1.metric(
        "RSI(14)",
        _fmt_metric_num(asset_technicals.get("rsi14"), "{:.1f}"),
        asset_technicals.get("rsi_signal", "").replace("_", " ") or None,
    )
    t2.metric(
        "Trend",
        (asset_technicals.get("trend") or "N/A").replace("_", " "),
    )
    t3.metric(
        "MACD signal",
        (asset_technicals.get("macd_signal") or "N/A").replace("_", " "),
    )
    t4.metric(
        "BB position",
        (asset_technicals.get("bb_position") or "N/A").replace("_", " "),
    )

if not asset_fundamentals and not asset_technicals:
    st.caption(
        "Fundamentals/technicals todavía no calculados. Ejecuta "
        "`python scripts/generate_cerebro_state.py` para refrescar."
    )

# ----------------------------------------------------------------------
# Block E — Noticias relevantes (per-asset, populated by news_scanner)
# ----------------------------------------------------------------------
st.markdown("<h2>Noticias Relevantes</h2>", unsafe_allow_html=True)

RELEVANCE_BADGE_COLORS = {"high": "red", "medium": "yellow", "low": "neutral"}

if asset_news:
    news_rows: list[str] = []
    for n in asset_news[:5]:
        relevance = (n.get("relevance") or "low").lower()
        rbadge = status_badge(
            relevance.upper(),
            RELEVANCE_BADGE_COLORS.get(relevance, "neutral"),
        )
        category = (n.get("category") or "other").replace("_", " ")
        source = n.get("source", "")
        ts_str = n.get("timestamp", "")[:16]
        summary = n.get("summary_1line") or n.get("headline", "")
        url = n.get("url", "#")
        link = (
            f"<a href='{url}' target='_blank' style='color:#3B82F6; "
            f"text-decoration:none; font-size:0.875rem;'>Leer →</a>"
            if url and url != "#" else ""
        )
        news_rows.append(
            f"""
            <div style="padding:10px 0; border-bottom:1px solid #1C2333;">
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap;">
                    {rbadge}
                    <span style='font-size:0.75rem; color:#94A0B8;'>{category} · {source} · {ts_str}</span>
                </div>
                <div style='color:#E8ECF4; line-height:1.5; font-size:0.9375rem;'>{summary}</div>
                <div style='margin-top:4px;'>{link}</div>
            </div>
            """
        )
    st.markdown(
        '<div class="institutional-card">' + "".join(news_rows) + "</div>",
        unsafe_allow_html=True,
    )
else:
    st.caption(
        f"Sin noticias materiales recientes para {selected} "
        "(últimos 7 días, relevance ≥ medium)."
    )

# ----------------------------------------------------------------------
# Block F — Eventos próximos (DINÁMICOS desde cerebro state)
# ----------------------------------------------------------------------
st.markdown("<h2>Eventos Próximos</h2>", unsafe_allow_html=True)

# `cerebro_state` was loaded once at the top of Bloque C.
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
            f"<span style='font-size:0.6875rem; color:#5C6378; margin-left:8px;'>[{source_label}]</span>"
            if source_label
            else ""
        )
        rows.append(
            f"""
            <div style="display:flex; gap:16px; padding:10px 0; border-bottom:1px solid #1C2333;">
                <div style="font-family:'JetBrains Mono', monospace; color:#3B82F6; font-weight:600; min-width:110px;">{evt.get('date', '—')}</div>
                <div style="color:#94A0B8; line-height:1.5; flex:1;">{evt.get('event', '—')}{source_badge}</div>
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
    help="Abre Pantalla 7 — Operaciones (registro manual).",
):
    st.switch_page("pages/7_Trades.py")

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
                <div class="institutional-card" style="background:#F0F9FF; border-left: 3px solid #3B82F6; margin-top:12px;">
                    <span style="font-size:0.75rem; color:#3B82F6; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Respuesta del cerebro</span>
                    <p style="margin:8px 0 0 0; color:#E8ECF4; line-height:1.6; font-size:0.9375rem; white-space:pre-wrap;">{answer}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if st.button("Cerrar chat", key=f"close_detalle_{selected}", type="secondary"):
            st.session_state.pop(f"chat_open_detalle_{selected}", None)
            st.session_state.pop(f"chat_answer_detalle_{selected}", None)
            st.rerun()

"""Pantalla 5 — Comparativa Portfolios.

Six blocks (A–F):
- A: Ranking 9 carteras (delta desde T0).
- B: Conclusión honesta (LLM si disponible, rule-based si no).
- C: Performance Attribution placeholder (≥30 días requeridos).
- D: Chart temporal (reusa el componente de Pantalla 1).
- E: Análisis por cartera (selectbox).
- F: Métricas de riesgo (solo real).
"""

from __future__ import annotations

import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from components.multi_portfolio_chart import render_chart  # noqa: E402
from services.cerebro_state import load_cerebro_state  # noqa: E402
from styles import (  # noqa: E402
    format_percent,
    inject_css,
)

st.set_page_config(
    page_title="Comparativa Portfolios",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

if not check_auth():
    st.stop()

state = load_cerebro_state()

st.markdown(
    "<h1 style='margin-bottom:0;'>Comparativa de Portfolios</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
    f"Última actualización {state['generated_at']}</p>",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Block A — Ranking
# ----------------------------------------------------------------------
st.markdown("<h2>Ranking</h2>", unsafe_allow_html=True)

period = st.radio(
    "Periodo de comparación:",
    options=["1D", "1S", "1M", "3M", "YTD", "1Y", "ALL"],
    index=6,
    horizontal=True,
    key="period_selector",
)
if period != "ALL":
    st.caption(
        f"El ranking siempre se mide desde T0 (delta acumulado). "
        f"El periodo {period} se activa cuando haya histórico ≥30 días."
    )

chart_data = state.get("portfolios_chart_data", {})
series_list = chart_data.get("series", []) or []

if series_list:
    ranking_data = []
    for s in series_list:
        vals = s.get("values") or []
        if not vals:
            continue
        t0 = vals[0]
        now = vals[-1]
        delta_pct = ((now - t0) / t0) * 100 if t0 else 0.0
        ranking_data.append(
            {
                "name": s["name"],
                "current": now,
                "delta_pct": delta_pct,
                "color": s.get("color", "#94A0B8"),
            }
        )
    ranking_data.sort(key=lambda x: x["delta_pct"], reverse=True)

    rows_html = ""
    for i, item in enumerate(ranking_data, 1):
        if item["delta_pct"] > 0:
            delta_color = "#10B981"
        elif item["delta_pct"] < 0:
            delta_color = "#EF4444"
        else:
            delta_color = "#94A0B8"
        is_user = item["name"] in ("real", "shadow")
        row_bg = "#131825" if is_user else "white"
        name_weight = "600" if is_user else "500"
        rows_html += (
            f'<tr style="background:{row_bg}; '
            f'border-bottom:1px solid #1C2333;">'
            f'<td style="padding:10px 12px; color:#94A0B8;'
            f' font-size:0.875rem;">{i}</td>'
            f'<td style="padding:10px 12px; color:#E8ECF4;'
            f' font-weight:{name_weight};">{item["name"]}</td>'
            f'<td style="padding:10px 12px; text-align:right;'
            f" font-family:'JetBrains Mono', monospace; "
            f'color:{delta_color}; font-weight:600;">'
            f'{item["delta_pct"]:+.2f}%</td>'
            f'<td style="padding:10px 12px; text-align:right;'
            f" font-family:'JetBrains Mono', monospace; "
            f'color:#94A0B8;">{item["current"]:.2f}</td>'
            f"</tr>"
        )

    table_html = (
        '<div class="institutional-card" style="padding:0;'
        " overflow:hidden;\">"
        '<table style="width:100%; border-collapse:collapse;">'
        '<thead><tr style="border-bottom:1px solid #2A3142;'
        ' background:#131825;">'
        '<th style="text-align:left; padding:8px 12px;'
        " font-size:0.75rem; color:#94A0B8; font-weight:600;"
        ' text-transform:uppercase; letter-spacing:0.05em;">#</th>'
        '<th style="text-align:left; padding:8px 12px;'
        " font-size:0.75rem; color:#94A0B8; font-weight:600;"
        ' text-transform:uppercase; letter-spacing:0.05em;">Cartera</th>'
        '<th style="text-align:right; padding:8px 12px;'
        " font-size:0.75rem; color:#94A0B8; font-weight:600;"
        ' text-transform:uppercase; letter-spacing:0.05em;">'
        "Delta desde T0</th>"
        '<th style="text-align:right; padding:8px 12px;'
        " font-size:0.75rem; color:#94A0B8; font-weight:600;"
        ' text-transform:uppercase; letter-spacing:0.05em;">'
        "Index actual</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
else:
    st.info("Sin datos suficientes para ranking. Snapshots necesarios.")

# ----------------------------------------------------------------------
# Block B — Conclusión honesta
# ----------------------------------------------------------------------
st.markdown("<h2>Conclusión Honesta</h2>", unsafe_allow_html=True)

comp = state.get("comparative_analysis", {}) or {}
if comp:
    src = comp.get("_narrative_source", "rule_based")
    src_badge = (
        "LLM" if src == "llm" else "DETERMINISTA"
    )
    src_color = "#3B82F6" if src == "llm" else "#94A0B8"
    st.markdown(
        f"""
        <div class="institutional-card" style="border-left: 3px solid #3B82F6;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
                <span class="status-badge" style="background:{src_color}1A; color:{src_color}; border:1px solid {src_color}40;">{src_badge}</span>
                <span style="font-size:0.75rem; color:#94A0B8;">Comparador del día: {comp.get('comparator_today', '—')}</span>
            </div>
            <h3 style="margin:0 0 12px 0; color:#E8ECF4; font-size:1.125rem; font-weight:600;">{comp.get('headline', '—')}</h3>
            <p style="color:#94A0B8; line-height:1.6; margin:0 0 16px 0; font-size:0.9375rem;">{comp.get('narrative', '—')}</p>
            <div style="background:#1E3A5F; padding:12px; border-radius:6px;">
                <span style="font-size:0.75rem; color:#3B82F6; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Acción</span>
                <p style="margin:4px 0 0 0; color:#1E3A5F; font-weight:500; font-size:0.9375rem;">{comp.get('action', '—')}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.info("Sin análisis comparativo disponible.")

# ----------------------------------------------------------------------
# Block C — Performance Attribution placeholder
# ----------------------------------------------------------------------
st.markdown("<h2>Performance Attribution</h2>", unsafe_allow_html=True)
st.markdown(
    """
    <div class="institutional-card" style="background:#131825;">
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
            <span class="status-badge" style="background:#94A0B81A; color:#94A0B8; border:1px solid #94A0B840;">PENDIENTE</span>
            <span style="font-size:0.75rem; color:#94A0B8; text-transform:uppercase; letter-spacing:0.05em;">Requiere ≥30 días de histórico</span>
        </div>
        <p style="margin:0; color:#94A0B8; line-height:1.6; font-size:0.9375rem;">
        Cuando esté disponible verás:
        <br>· Brinson-Fachler decomposition (stock picking vs sector allocation vs market timing)
        <br>· Fama-French 5 + Carhart momentum factor regression con alpha
        <br>· Bootstrap CIs sobre Sharpe / Sortino
        <br>· Comparación causal con cada paper portfolio
        <br><br>
        Disponibilidad estimada: ~2026-06-12 (30 días desde T0 = 2026-05-11).
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Block D — Chart temporal (reuses Pantalla 1 component)
# ----------------------------------------------------------------------
st.markdown("<h2>Performance Temporal</h2>", unsafe_allow_html=True)
render_chart(chart_data)

# ----------------------------------------------------------------------
# Block E — Análisis por cartera (selectbox)
# ----------------------------------------------------------------------
st.markdown("<h2>Análisis por Cartera</h2>", unsafe_allow_html=True)

PORTFOLIO_NARRATIVES: dict[str, dict[str, str]] = {
    "real": {
        "label": "Tu cartera real",
        "description": (
            "19 posiciones reales en Lightyear. Stock picking individual + 5 day-trades el 2026-05-12."
        ),
        "why_diff": (
            "Es la base; las demás carteras son referencias para evaluar tu skill neta."
        ),
    },
    "shadow": {
        "label": "Shadow (réplica saneada)",
        "description": (
            "Misma composición que real con sanitización: caps de Tech / USD respetados, "
            "buffer MMF, sin override AXON."
        ),
        "why_diff": (
            "Shadow expone tu cartera real saneada como upper bound de tu propio stock picking. "
            "Si shadow gana consistentemente, tu sesgo de concentración te está costando."
        ),
    },
    "quality": {
        "label": "Quality (Novy-Marx GP/A)",
        "description": (
            "20 names top-decile GP/A. Currently 100% cash (50k EUR) tras red-team BLOCK; "
            "pendiente v3 deployment con metodología revisada."
        ),
        "why_diff": (
            "Cuando despliegue, mostrará si el quality factor bate tu stock picking discrecional."
        ),
    },
    "value": {
        "label": "Value (Magic Formula EY+ROC)",
        "description": (
            "15 names Magic Formula Greenblatt. Currently 100% cash tras red-team BLOCK A2/A6; "
            "pendiente literatura review."
        ),
        "why_diff": (
            "Cuando despliegue, mostrará si el value factor bate tu stock picking discrecional."
        ),
    },
    "momentum": {
        "label": "Momentum (AMP MOM 2,12)",
        "description": (
            "20-25 names top-decile momentum 12-1, US-only. Pending deployment Fase D."
        ),
        "why_diff": (
            "Si momentum gana, indica que tu cartera podría beneficiarse de tilt momentum."
        ),
    },
    "aggressive": {
        "label": "Aggressive (DIAGNOSTIC sleeve)",
        "description": (
            "Composite high-beta + sales growth + low-FCF. Diagnostic, no playable como cartera."
        ),
        "why_diff": (
            "Diagnostica la parte aggressive de tu real (~30% en IREN/KTOS/OUST/AXON/PGY)."
        ),
    },
    "conservative": {
        "label": "Conservative (Path B QMJ+LowVol+Bonds)",
        "description": (
            "60% equity QMJ+LowVol + 40% bond sleeve (IEAG/TIPS/USD-hedged). Pending deploy."
        ),
        "why_diff": (
            "Si conservative gana en stress, sugiere añadir bond sleeve a tu real."
        ),
    },
    "benchmark_passive": {
        "label": "Benchmark Passive",
        "description": (
            "70% IWDA + 20% VFEM + 10% IEAG, buy-and-hold rebalanceo anual."
        ),
        "why_diff": (
            "Si benchmark gana, tus trades destruyen valor: el coste/rotación no compensa el alpha."
        ),
    },
    "robo_advisor": {
        "label": "Robo-Advisor (Indexa agressive)",
        "description": (
            "65% IWDA + 15% VFEM + 10% XESC + 10% EUNH con 0.40% AuM fee continuo."
        ),
        "why_diff": (
            "Mide si tu skill bate el coste de un asesor automatizado (vs benchmark pasivo + fee)."
        ),
    },
}

selected = st.selectbox(
    "Selecciona cartera:",
    options=list(PORTFOLIO_NARRATIVES.keys()),
    format_func=lambda x: PORTFOLIO_NARRATIVES[x]["label"],
    key="portfolio_selector",
)

if selected:
    info = PORTFOLIO_NARRATIVES[selected]
    s_series = next(
        (s for s in series_list if s["name"] == selected), None
    )
    if s_series and s_series["values"]:
        v0 = s_series["values"][0]
        vn = s_series["values"][-1]
        delta = ((vn - v0) / v0) * 100 if v0 else 0.0
        if delta > 0:
            delta_color = "#10B981"
        elif delta < 0:
            delta_color = "#EF4444"
        else:
            delta_color = "#94A0B8"
    else:
        delta = 0.0
        delta_color = "#94A0B8"

    st.markdown(
        f"""
        <div class="institutional-card">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
                <h3 style="margin:0; color:#E8ECF4; font-size:1.125rem; font-weight:600;">{info['label']}</h3>
                <span style="font-family:'JetBrains Mono', monospace; color:{delta_color}; font-weight:600; font-size:1.125rem;">{delta:+.2f}%</span>
            </div>
            <p style="color:#94A0B8; line-height:1.6; margin:0 0 12px 0; font-size:0.9375rem;"><strong>Estrategia:</strong> {info['description']}</p>
            <div style="background:#131825; padding:12px; border-radius:6px;">
                <span style="font-size:0.75rem; color:#94A0B8; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;">Por qué la diferencia con tu real</span>
                <p style="margin:6px 0 0 0; color:#94A0B8; font-size:0.9375rem; line-height:1.5;">{info['why_diff']}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------
# Block F — Métricas de riesgo (solo real)
# ----------------------------------------------------------------------
st.markdown(
    "<h2>Métricas de Riesgo (cartera real)</h2>", unsafe_allow_html=True
)

p = state.get("portfolio_real", {}) or {}
col1, col2, col3 = st.columns(3)
col1.metric(
    "Drawdown actual vs peak",
    format_percent(p.get("drawdown_current_pct", 0.0)),
    help=f"Peak en {p.get('drawdown_from_peak', '—')}",
)
col2.metric(
    "Cash buffer",
    format_percent(p.get("cash_pct_nav", 0.0), show_sign=False),
    help="Líquido disponible",
)
col3.metric(
    "Posiciones activas",
    p.get("positions_count", 0),
)

st.caption(
    "Métricas avanzadas (volatilidad anualizada, Sharpe, Sortino, "
    "VaR/CVaR) requieren ≥30 días de datos. Disponibles ~2026-06-12."
)

"""Pantalla 8 — Tesis Browser (histórico + timeline + filtros).

Read-only UI on top of `dashboard/services/thesis_browser.ThesisBrowser`.
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

import streamlit as st  # noqa: E402

from auth import check_auth  # noqa: E402
from services.thesis_browser import ThesisBrowser  # noqa: E402
from styles import inject_css, status_badge  # noqa: E402


st.set_page_config(
    page_title="Tesis Browser",
    page_icon=":books:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

if not check_auth():
    st.stop()


browser = ThesisBrowser()
all_assets = browser.list_all_assets_with_theses()


# ----------------------------------------------------------------------
# Block A — Header + KPIs
# ----------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0;'>Tesis Browser</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#94A0B8; margin-top:4px; font-size:0.9375rem;'>"
    "Histórico de tesis con timeline y filtros. Read-only.</p>",
    unsafe_allow_html=True,
)

n_total = len(all_assets)
n_active = sum(1 for a in all_assets if a["status"] == "active")
n_closed = sum(1 for a in all_assets if a["status"] == "closed")
n_halfway = sum(1 for a in all_assets if a["status"] == "halfway_active")
n_override = sum(1 for a in all_assets if a["status"] == "override_active")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tesis total", n_total)
c2.metric("Activas", n_active)
c3.metric("Cerradas", n_closed)
c4.metric("Halfway falsifier", n_halfway)
c5.metric("Override activo", n_override)


# ----------------------------------------------------------------------
# Block B — Filters
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("### Buscar y filtrar")

if not all_assets:
    st.info("Sin tesis registradas todavía.")
    st.stop()

f1, f2, f3, f4, f5 = st.columns(5)
search = f1.text_input("Buscar ticker", placeholder="MSFT, MELI…")
status_options = [""] + browser.get_distinct_values("status")
status_filter = f2.selectbox(
    "Status",
    options=status_options,
    format_func=lambda s: s.replace("_", " ") if s else "Todos",
)
rec_options = [""] + browser.get_distinct_values("recommendation")
rec_filter = f3.selectbox(
    "Recommendation",
    options=rec_options,
    format_func=lambda s: s if s else "Todas",
)
sector_options = [""] + browser.get_distinct_values("sector")
sector_filter = f4.selectbox(
    "Sector",
    options=sector_options,
    format_func=lambda s: s if s else "Todos",
)
country_options = [""] + browser.get_distinct_values("country")
country_filter = f5.selectbox(
    "País",
    options=country_options,
    format_func=lambda s: s if s else "Todos",
)

filtered = browser.filter_assets(
    status=status_filter or None,
    recommendation=rec_filter or None,
    sector=sector_filter or None,
    country=country_filter or None,
    search_query=search or None,
)
st.caption(f"Mostrando {len(filtered)} de {n_total} tesis.")


# ----------------------------------------------------------------------
# Block C — Asset list (clickable)
# ----------------------------------------------------------------------
STATUS_COLORS = {
    "active": "green",
    "halfway_active": "yellow",
    "override_active": "orange",
    "closed": "neutral",
    "no_thesis": "neutral",
}

REC_COLORS = {
    "buy": "green",
    "buy_more": "green",
    "add": "green",
    "watch": "yellow",
    "hold": "yellow",
    "reduce": "orange",
    "exit": "red",
    "sell": "red",
}


def _confidence_str(c: float | str | None) -> str:
    if c is None:
        return "—"
    if isinstance(c, (int, float)):
        return f"{float(c):.2f}"
    return str(c)


for asset in filtered:
    ticker = asset["ticker"]
    status = asset["status"]
    rec = asset["recommendation"]
    sector = asset["sector"]
    country = asset["country"]
    conf = _confidence_str(asset["confidence_calibrated"])

    status_badge_html = status_badge(
        status.upper().replace("_", " "),
        STATUS_COLORS.get(status, "neutral"),
    )
    rec_color = REC_COLORS.get(str(rec).lower(), "neutral")
    rec_badge_html = status_badge(str(rec).upper(), rec_color)

    col_main, col_btn = st.columns([5, 1])
    with col_main:
        st.markdown(
            f"""
            <div class="institutional-card">
                <div style="display:flex; justify-content:space-between;
                            align-items:center; flex-wrap:wrap; gap:8px;">
                    <div>
                        <span style="font-family:'JetBrains Mono', monospace;
                                     font-size:1rem; font-weight:600; color:#E8ECF4;">
                            {ticker}
                        </span>
                        <span style="margin-left:12px; font-size:0.85rem;
                                     color:#94A0B8;">{sector} · {country}</span>
                    </div>
                    <div style="display:flex; gap:8px; align-items:center;
                                flex-wrap:wrap;">
                        {status_badge_html}
                        {rec_badge_html}
                        <span style="font-size:0.75rem; color:#94A0B8;">
                            confianza {conf} · {asset['n_events']} events ·
                            {asset['last_event_date']}
                        </span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button(
            "Timeline", key=f"timeline_{ticker}", use_container_width=True
        ):
            st.session_state.selected_thesis_ticker = ticker


# ----------------------------------------------------------------------
# Block D — Timeline drill-down
# ----------------------------------------------------------------------
selected = st.session_state.get("selected_thesis_ticker")
if selected:
    st.markdown("---")
    st.markdown(f"### Timeline — {selected}")
    if st.button("Cerrar timeline", key="close_timeline"):
        del st.session_state.selected_thesis_ticker
        st.rerun()

    timeline = browser.get_timeline(selected)
    if not timeline:
        st.info("Sin eventos para este ticker.")
    else:
        for ev in timeline:
            ev_type = ev.get("event_type", "unknown")
            ts = (ev.get("timestamp") or "")[:19].replace("T", " ")
            ev_id = (ev.get("event_id") or "")[:12]

            color = {
                "thesis": "blue",
                "thesis_review": "blue",
                "thesis_user_override_annotation": "orange",
                "thesis_position_size_change": "neutral",
                "thesis_closed_position": "neutral",
            }.get(ev_type, "neutral")

            badge_html = status_badge(
                ev_type.upper().replace("_", " "), color
            )
            details_parts: list[str] = []
            rec = ev.get("recommendation") or ev.get("recommendation_v2")
            if rec:
                details_parts.append(
                    f"<span style='color:#94A0B8;'>Rec:</span> "
                    f"<strong>{rec}</strong>"
                )
            cf = ev.get("confidence_calibrated")
            if cf is not None:
                details_parts.append(
                    f"<span style='color:#94A0B8;'>Conf:</span> "
                    f"<strong>{_confidence_str(cf)}</strong>"
                )
            tv = ev.get("thesis_version")
            if tv:
                details_parts.append(
                    f"<span style='color:#94A0B8;'>Version:</span> "
                    f"<strong>{tv}</strong>"
                )
            details_html = " · ".join(details_parts)

            summary = (
                ev.get("note")
                or ev.get("confidence_justification")
                or ""
            )
            if isinstance(summary, dict):
                summary = ""
            summary_html = (
                f"<p style='margin:8px 0 0 0; color:#94A0B8; "
                f"font-size:0.9rem; line-height:1.5; "
                f"white-space:pre-wrap;'>{str(summary)[:400]}</p>"
                if summary else ""
            )

            st.markdown(
                f"""
                <div class="institutional-card" style="margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between;
                                align-items:center; flex-wrap:wrap; gap:8px;">
                        <div>
                            {badge_html}
                            <span style="margin-left:8px;
                                         font-family:'JetBrains Mono', monospace;
                                         font-size:0.75rem; color:#94A0B8;">{ts}</span>
                        </div>
                        <span style="font-family:'JetBrains Mono', monospace;
                                     font-size:0.7rem; color:#5C6378;">{ev_id}</span>
                    </div>
                    <div style="margin-top:6px; font-size:0.85rem;">{details_html}</div>
                    {summary_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

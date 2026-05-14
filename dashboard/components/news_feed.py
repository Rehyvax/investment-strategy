"""Block F — News feed (institutional list, relevance badge)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from styles import status_badge

RELEVANCE_STATUS = {"high": "red", "medium": "yellow", "low": "neutral"}


def render_news_feed(news: list[dict]) -> None:
    st.markdown("<h2>Noticias Relevantes</h2>", unsafe_allow_html=True)

    if not news:
        st.info("Sin noticias materiales del día.")
        return

    for item in news[:5]:
        ts_raw = item["timestamp"].replace("Z", "+00:00")
        try:
            ts_str = datetime.fromisoformat(ts_raw).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            ts_str = item["timestamp"]
        relevance_badge = status_badge(
            item["relevance"].upper(),
            RELEVANCE_STATUS.get(item["relevance"], "neutral"),
        )

        with st.expander(
            f"{item['asset']} — {item['headline']}", expanded=False
        ):
            st.markdown(
                f"""
                <div style="margin-bottom:8px;">
                    {relevance_badge}
                    <span style="font-size:0.75rem; color:#94A0B8; margin-left:8px;">
                        {item['source']} · {ts_str}
                    </span>
                </div>
                <a href="{item['url']}" target="_blank" style="color:#3B82F6; text-decoration:none; font-size:0.9375rem;">
                    Leer artículo completo →
                </a>
                """,
                unsafe_allow_html=True,
            )

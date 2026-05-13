"""Bloque F — News feed filtered by held assets."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

RELEVANCE_ICON = {"high": "🔴", "medium": "🟡", "low": "⚪"}


def render_news_feed(news: list[dict]) -> None:
    st.subheader("Noticias relevantes")

    for item in news[:5]:
        icon = RELEVANCE_ICON.get(item["relevance"], "⚪")
        with st.expander(
            f"{icon} **{item['asset']}** — {item['headline']}"
        ):
            ts_raw = item["timestamp"].replace("Z", "+00:00")
            try:
                ts = datetime.fromisoformat(ts_raw)
                st.caption(
                    f"{item['source']} · {ts.strftime('%Y-%m-%d %H:%M')}"
                )
            except ValueError:
                st.caption(item["source"])
            st.markdown(f"[Leer artículo completo]({item['url']})")

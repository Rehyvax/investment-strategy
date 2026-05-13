"""Smoke tests for Home Cockpit components (institutional UI).

Each component is rendered against a minimal inline fixture inside the
runner closure; AppTest.from_function lifts the runner's source into a
fresh script, so any helper used must be defined inside the closure.
"""

from __future__ import annotations

import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))


def _all_markdown_text(at) -> str:
    """Concatenate every markdown payload rendered by the runner so tests
    can grep across both plain markdown and unsafe-HTML strings."""
    return "\n".join(m.value for m in at.markdown if m.value)


def test_market_status_renders():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.market_status import render_market_status

        data = {
            "regime": "risk_on_moderate",
            "regime_color": "green",
            "explanation": "Risk-on moderado.",
            "money_flow": "Tech lidera.",
            "fear_level": "low",
            "vix": 14.3,
            "bond_equity_ratio_30d": -0.12,
            "fear_summary": "VIX calmo.",
        }
        render_market_status(data)

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    text = _all_markdown_text(at)
    assert "Estado del Mercado" in text
    assert "Risk-On Moderado" in text
    assert "Flujo de capital" in text


def test_portfolio_summary_renders():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.portfolio_summary import render_portfolio_summary

        data = {
            "nav_total_eur": 47864.65,
            "nav_delta_1d_pct": 0.0,
            "nav_delta_1w_pct": -0.5,
            "nav_delta_1m_pct": 1.2,
            "nav_delta_ytd_pct": 0.5,
            "health_status": "green",
            "health_summary": "Sin breaches.",
            "drawdown_current_pct": -1.2,
            "drawdown_from_peak": "2026-05-08",
            "cash_eur": 2962.82,
            "cash_pct_nav": 6.2,
            "positions_count": 19,
        }
        render_portfolio_summary(data)

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    metric_labels = [m.label for m in at.metric]
    assert "NAV Total" in metric_labels
    assert "Posiciones activas" in metric_labels


def test_tax_alerts_renders():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.tax_alerts import render_tax_alerts

        render_tax_alerts(
            [
                {
                    "asset": "MELI",
                    "alert_type": "2_month_rule",
                    "message": "Test alert",
                    "expires": "2026-07-11",
                }
            ]
        )

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    text = _all_markdown_text(at)
    assert "Alertas Fiscales" in text
    assert "MELI" in text
    assert "Test alert" in text


def test_chart_renders_with_default_visible():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.multi_portfolio_chart import render_chart

        data = {
            "labels": ["2026-05-11", "2026-05-12"],
            "series": [
                {
                    "name": "real",
                    "values": [100.0, 100.5],
                    "color": "#1f77b4",
                    "default_visible": True,
                },
                {
                    "name": "shadow",
                    "values": [100.0, 100.6],
                    "color": "#ff7f0e",
                    "default_visible": False,
                },
            ],
        }
        render_chart(data)

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    text = _all_markdown_text(at)
    assert "Performance Comparativo" in text


def test_recommendations_top_3_only():
    """Even if 5 recommendations are passed, only 3 cards should render."""
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.recommendations import render_recommendations

        recs = [
            {
                "id": f"rec_{i}",
                "type": "HOLD",
                "asset": f"T{i}",
                "priority": "medium",
                "headline": f"Headline {i}",
                "narrative": "N",
                "action": "A",
                "color": "yellow",
            }
            for i in range(5)
        ]
        render_recommendations(recs)

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    text = _all_markdown_text(at)
    # Each card emits its own `institutional-card` block. We expect 3.
    assert text.count("institutional-card") == 3
    # And only the first 3 headlines should appear (Headline 0/1/2).
    assert "Headline 0" in text
    assert "Headline 2" in text
    assert "Headline 3" not in text


def test_comparative_renders():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.comparative import render_comparative

        render_comparative(
            {
                "headline": "Headline test",
                "narrative": "Narrative content",
                "comparator_today": "shadow",
                "comparator_reason": "Reason",
                "action": "Action text",
            }
        )

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    text = _all_markdown_text(at)
    assert "Análisis Comparativo" in text
    assert "Headline test" in text
    assert "Action text" in text


def test_news_feed_renders():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.news_feed import render_news_feed

        render_news_feed(
            [
                {
                    "asset": "MSFT",
                    "headline": "Test",
                    "timestamp": "2026-05-13T15:23:00Z",
                    "source": "Reuters",
                    "url": "https://example.com",
                    "relevance": "high",
                }
            ]
        )

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    text = _all_markdown_text(at)
    assert "Noticias Relevantes" in text

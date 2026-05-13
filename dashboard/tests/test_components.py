"""Smoke tests for Home Cockpit components.

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
    subheaders = [s.value for s in at.subheader]
    assert any("Estado del mercado" in s for s in subheaders)


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
    assert "NAV total" in metric_labels


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
    warnings = [w.value for w in at.warning]
    assert any("MELI" in w for w in warnings)


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


def test_recommendations_top_3_only():
    """Even if 5 recommendations are passed, only 3 should be rendered."""
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
    h3_count = sum(
        1 for m in at.markdown if m.value.startswith("### ")
    )
    assert h3_count == 3


def test_comparative_renders():
    from streamlit.testing.v1 import AppTest

    def runner():
        from components.comparative import render_comparative

        render_comparative(
            {
                "headline": "Headline test",
                "narrative": "Narrative",
                "comparator_today": "shadow",
                "comparator_reason": "Reason",
                "action": "Action",
            }
        )

    at = AppTest.from_function(runner)
    at.run()
    assert not at.exception
    successes = [s.value for s in at.success]
    assert any("Action" in s for s in successes)


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

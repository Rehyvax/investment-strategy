"""Design system for the dashboard.

Centralizes color palette, typography and CSS so every component
renders with the same institutional look (Schwab / IBKR / Empower
wealth-management aesthetic).
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Color palette
# ----------------------------------------------------------------------
COLOR_PRIMARY = "#1E40AF"
COLOR_PRIMARY_DARK = "#1E3A8A"
COLOR_PRIMARY_LIGHT = "#DBEAFE"

COLOR_TEXT_PRIMARY = "#0F172A"
COLOR_TEXT_SECONDARY = "#475569"
COLOR_TEXT_TERTIARY = "#94A3B8"

COLOR_BG_PRIMARY = "#FFFFFF"
COLOR_BG_SECONDARY = "#F8FAFC"
COLOR_BG_TERTIARY = "#F1F5F9"

COLOR_BORDER = "#E2E8F0"
COLOR_BORDER_HOVER = "#CBD5E1"

COLOR_POSITIVE = "#15803D"
COLOR_NEGATIVE = "#B91C1C"
COLOR_NEUTRAL = "#64748B"
COLOR_WARNING = "#A16207"

STATUS_COLORS = {
    "green": COLOR_POSITIVE,
    "yellow": COLOR_WARNING,
    "orange": "#C2410C",
    "red": COLOR_NEGATIVE,
    "blue": COLOR_PRIMARY,
    "neutral": COLOR_NEUTRAL,
}

# ----------------------------------------------------------------------
# Typography
# ----------------------------------------------------------------------
FONT_SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "JetBrains Mono, 'SF Mono', Menlo, monospace"

# ----------------------------------------------------------------------
# CSS bundle injected once per page
# ----------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    .institutional-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }

    .status-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    h1, h2, h3 {
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #0F172A;
    }

    h1 {
        font-size: 1.75rem;
        margin-bottom: 0.5rem;
    }

    h2 {
        font-size: 1.25rem;
        color: #475569;
        font-weight: 500;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #E2E8F0;
    }

    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace;
        font-feature-settings: 'tnum';
        font-size: 1.5rem;
        color: #0F172A;
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.875rem;
        color: #64748B;
        font-weight: 500;
    }

    [data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', monospace;
        font-feature-settings: 'tnum';
    }

    .stButton > button {
        background: #1E40AF;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.25rem;
        font-weight: 500;
        font-size: 0.875rem;
        transition: background 0.15s;
    }

    .stButton > button:hover {
        background: #1E3A8A;
    }

    .stButton > button[kind="secondary"] {
        background: white;
        color: #475569;
        border: 1px solid #CBD5E1;
    }

    .stButton > button[kind="secondary"]:hover {
        background: #F8FAFC;
        border-color: #94A3B8;
    }

    section[data-testid="stSidebar"] {
        background: #F8FAFC;
        border-right: 1px solid #E2E8F0;
    }

    hr {
        margin: 2rem 0;
        border-color: #E2E8F0;
    }
</style>
"""


def inject_css() -> None:
    """Inject institutional CSS. Call once near the top of each page."""
    import streamlit as st

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def status_badge(label: str, status: str = "neutral") -> str:
    """Return HTML for a sober status badge (replaces emoji indicators)."""
    color = STATUS_COLORS.get(status, COLOR_NEUTRAL)
    return (
        f'<span class="status-badge" '
        f'style="background: {color}1A; color: {color}; '
        f'border: 1px solid {color}40;">{label}</span>'
    )


def format_currency_eur(value: float | None, decimals: int = 0) -> str:
    """Format a EUR amount with thin-space separators."""
    if value is None:
        return "—"
    formatted = f"{value:,.{decimals}f}".replace(",", " ")
    return f"€{formatted}"


def format_percent(
    value: float | None, decimals: int = 2, show_sign: bool = True
) -> str:
    """Format a percent with consistent decimals and optional sign."""
    if value is None:
        return "—"
    sign = "+" if show_sign and value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"

"""Design system for the dashboard — Slate Pro dark theme.

Backwards-compatible API: every constant and helper that previously
lived in `dashboard/styles.py` is re-exported from here so
`from styles import COLOR_TEXT_PRIMARY` keeps working with new
dark-mode color values.

The single source of truth for raw hex values is `palette.py`.
"""

from __future__ import annotations

from .palette import (  # noqa: F401 — re-exports
    ACCENT_HOVER,
    ACCENT_MUTED,
    ACCENT_PRIMARY,
    BACKGROUND_ELEVATED,
    BACKGROUND_PRIMARY,
    BACKGROUND_SECONDARY,
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    CHART_COLORS,
    DANGER_BRIGHT,
    DANGER_LOSS,
    STATUS_BADGE_COLORS,
    SUCCESS_BRIGHT,
    SUCCESS_POSITIVE,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    WARNING_BRIGHT,
    WARNING_NEUTRAL,
)


# ----------------------------------------------------------------------
# Backwards-compat aliases (existing pages import these names)
# ----------------------------------------------------------------------
COLOR_PRIMARY = ACCENT_PRIMARY
COLOR_PRIMARY_DARK = ACCENT_MUTED
COLOR_PRIMARY_LIGHT = ACCENT_HOVER

COLOR_TEXT_PRIMARY = TEXT_PRIMARY
COLOR_TEXT_SECONDARY = TEXT_SECONDARY
COLOR_TEXT_TERTIARY = TEXT_TERTIARY

COLOR_BG_PRIMARY = BACKGROUND_PRIMARY
COLOR_BG_SECONDARY = BACKGROUND_SECONDARY
COLOR_BG_TERTIARY = BACKGROUND_ELEVATED

COLOR_BORDER = BORDER_SUBTLE
COLOR_BORDER_HOVER = BORDER_DEFAULT

COLOR_POSITIVE = SUCCESS_POSITIVE
COLOR_NEGATIVE = DANGER_LOSS
COLOR_NEUTRAL = TEXT_SECONDARY
COLOR_WARNING = WARNING_NEUTRAL

STATUS_COLORS = dict(STATUS_BADGE_COLORS)


# ----------------------------------------------------------------------
# Typography
# ----------------------------------------------------------------------
FONT_SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "JetBrains Mono, 'SF Mono', Menlo, monospace"


# ----------------------------------------------------------------------
# CSS bundle injected once per page — Slate Pro dark mode
# ----------------------------------------------------------------------
CUSTOM_CSS = f"""
<style>
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: {TEXT_PRIMARY};
    }}

    .stApp {{
        background-color: {BACKGROUND_PRIMARY};
    }}

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}

    /* Streamlit Cloud header: keep the sidebar-toggle button visible
       (children with collapsedControl test-id), hide only the deploy
       toolbar so the chrome stays clean. Previously `header {{visibility:
       hidden;}}` killed the entire bar including the toggle, leaving the
       user with no way to reopen a collapsed sidebar on narrow widths. */
    header[data-testid="stHeader"] {{
        background: transparent;
        height: 2.5rem;
    }}
    [data-testid="stToolbar"] {{display: none !important;}}
    [data-testid="stDecoration"] {{display: none !important;}}

    .main .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
        /* Defensive — prevents long unbroken strings (URLs, tickers,
           narrative paragraphs from llm_narratives) from overflowing
           the right edge on narrow viewports. */
        overflow-wrap: anywhere;
        word-break: break-word;
    }}

    .institutional-card {{
        background: {BACKGROUND_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        color: {TEXT_PRIMARY};
        overflow-wrap: anywhere;
        word-break: break-word;
    }}

    .status-badge {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    h1, h2, h3, h4, h5, h6 {{
        font-weight: 600;
        letter-spacing: -0.02em;
        color: {TEXT_PRIMARY};
    }}

    h1 {{
        font-size: 1.75rem;
        margin-bottom: 0.5rem;
    }}

    h2 {{
        font-size: 1.25rem;
        color: {TEXT_SECONDARY};
        font-weight: 500;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid {BORDER_SUBTLE};
    }}

    p, span, div, li {{
        color: {TEXT_PRIMARY};
    }}

    [data-testid="stMetricValue"] {{
        font-family: 'JetBrains Mono', monospace;
        font-feature-settings: 'tnum';
        font-size: 1.5rem;
        color: {TEXT_PRIMARY};
    }}

    [data-testid="stMetricLabel"] {{
        font-size: 0.875rem;
        color: {TEXT_SECONDARY};
        font-weight: 500;
    }}

    [data-testid="stMetricDelta"] {{
        font-family: 'JetBrains Mono', monospace;
        font-feature-settings: 'tnum';
    }}

    .stButton > button {{
        background: {ACCENT_PRIMARY};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.25rem;
        font-weight: 500;
        font-size: 0.875rem;
        transition: background 0.15s;
    }}

    .stButton > button:hover {{
        background: {ACCENT_HOVER};
    }}

    .stButton > button[kind="secondary"] {{
        background: {BACKGROUND_ELEVATED};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_DEFAULT};
    }}

    .stButton > button[kind="secondary"]:hover {{
        background: {BACKGROUND_SECONDARY};
        border-color: {ACCENT_PRIMARY};
    }}

    section[data-testid="stSidebar"] {{
        background: {BACKGROUND_SECONDARY};
        border-right: 1px solid {BORDER_SUBTLE};
    }}

    section[data-testid="stSidebar"] * {{
        color: {TEXT_PRIMARY};
    }}

    section[data-testid="stSidebar"] .stCaption {{
        color: {TEXT_SECONDARY};
    }}

    /* Streamlit default text widgets */
    .stMarkdown, .stCaption, .stText {{
        color: {TEXT_PRIMARY};
    }}

    /* Dataframes */
    [data-testid="stDataFrame"] {{
        background: {BACKGROUND_ELEVATED};
    }}

    /* Inputs */
    .stTextInput input, .stTextArea textarea, .stNumberInput input,
    .stDateInput input, .stSelectbox div[data-baseweb="select"] {{
        background: {BACKGROUND_ELEVATED} !important;
        color: {TEXT_PRIMARY} !important;
        border-color: {BORDER_DEFAULT} !important;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {TEXT_SECONDARY};
    }}
    .stTabs [aria-selected="true"] {{
        color: {ACCENT_PRIMARY};
    }}

    /* Expander */
    .streamlit-expanderHeader {{
        background: {BACKGROUND_ELEVATED};
        color: {TEXT_PRIMARY};
    }}

    /* Alerts (st.info / st.warning / st.success / st.error) */
    .stAlert {{
        background: {BACKGROUND_ELEVATED} !important;
        color: {TEXT_PRIMARY} !important;
        border-left-width: 3px;
        overflow-wrap: anywhere;
        word-break: break-word;
    }}

    hr {{
        margin: 2rem 0;
        border-color: {BORDER_SUBTLE};
    }}

    /* Plotly background transparent so the app canvas shows through */
    .js-plotly-plot, .plot-container {{
        background: transparent !important;
    }}

    /* Chat input on Pantalla 6 */
    .stChatInput {{
        background: {BACKGROUND_ELEVATED};
    }}
</style>
"""


def inject_css() -> None:
    """Inject Slate Pro CSS. Call once near the top of each page."""
    import streamlit as st

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def flat_html(s: str) -> str:
    """Collapse a multi-line HTML string into a single line so Streamlit's
    markdown processor does not parse indented HTML as a fenced code block.

    Streamlit 1.50+ uses markdown-it-py, which treats lines with 4+ leading
    spaces as indented-code blocks even when surrounding lines are HTML —
    the failure mode is literal `</span></div>` leaking into the rendered
    page (observed in Pantalla 3 Detalle and Pantalla 8 Tesis after the
    Slate Pro CSS rewrite).

    Stripping per-line whitespace preserves HTML semantics (browsers collapse
    inter-tag whitespace) while keeping markdown-it-py from mis-tokenizing
    the block. Use on every `st.markdown(f\"\"\"...\"\"\", unsafe_allow_html=True)`
    call whose f-string spans more than one line."""
    return "".join(line.strip() for line in s.splitlines())


def status_badge(label: str, status: str = "neutral") -> str:
    """Return HTML for a sober status badge.

    Uses 1A (10%) alpha tint for the fill and 40 (25%) alpha for the
    border so badges read on the dark canvas without being flat blocks.
    """
    color = STATUS_BADGE_COLORS.get(status, TEXT_SECONDARY)
    return (
        f'<span class="status-badge" '
        f'style="background: {color}26; color: {color}; '
        f'border: 1px solid {color}55;">{label}</span>'
    )


def format_currency_eur(value: float | None, decimals: int = 0) -> str:
    """Format a EUR amount with thin-space separators."""
    if value is None:
        return "—"
    formatted = f"{value:,.{decimals}f}".replace(",", " ")
    return f"€{formatted}"


def format_percent(
    value: float | None, decimals: int = 2, show_sign: bool = True
) -> str:
    """Format a percent with consistent decimals and optional sign."""
    if value is None:
        return "—"
    sign = "+" if show_sign and value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"

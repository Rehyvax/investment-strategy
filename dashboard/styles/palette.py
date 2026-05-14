"""Slate Pro palette — Bloomberg-Terminal-inspired dark mode.

Single source of truth for every color rendered by the dashboard.
Imported re-exports live in `dashboard/styles/__init__.py` so existing
`from styles import COLOR_*` callers keep working with the dark-mode
equivalents.

Contrast (WCAG AAA target ≥7:1 for body text):
    TEXT_PRIMARY  E8ECF4 on BACKGROUND_PRIMARY 0A0E1A → 14.5:1  (AAA)
    TEXT_SECONDARY 94A0B8 on BACKGROUND_PRIMARY 0A0E1A → 7.4:1  (AAA)
    TEXT_TERTIARY  5C6378 on BACKGROUND_PRIMARY 0A0E1A → 3.4:1  (AA UI)
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Backgrounds / surfaces
# ----------------------------------------------------------------------
BACKGROUND_PRIMARY = "#0A0E1A"     # app canvas
BACKGROUND_SECONDARY = "#131825"   # sidebar, secondary panels
BACKGROUND_ELEVATED = "#1C2333"    # cards, modals

BORDER_SUBTLE = "#2A3142"          # card edges
BORDER_DEFAULT = "#3A4258"         # inputs, dividers

# ----------------------------------------------------------------------
# Text
# ----------------------------------------------------------------------
TEXT_PRIMARY = "#E8ECF4"
TEXT_SECONDARY = "#94A0B8"
TEXT_TERTIARY = "#5C6378"
TEXT_DISABLED = "#3A4258"

# ----------------------------------------------------------------------
# Accent (brand)
# ----------------------------------------------------------------------
ACCENT_PRIMARY = "#3B82F6"
ACCENT_HOVER = "#60A5FA"
ACCENT_MUTED = "#1E3A5F"           # subdued accent fills (confirm panels)

# ----------------------------------------------------------------------
# State
# ----------------------------------------------------------------------
SUCCESS_POSITIVE = "#10B981"
SUCCESS_BRIGHT = "#34D399"
WARNING_NEUTRAL = "#F59E0B"
WARNING_BRIGHT = "#FBBF24"
DANGER_LOSS = "#EF4444"
DANGER_BRIGHT = "#F87171"

# ----------------------------------------------------------------------
# Per-portfolio chart colors (consumed by Pantalla 5 + cerebro generator)
# ----------------------------------------------------------------------
CHART_COLORS: dict[str, str] = {
    "real": "#3B82F6",                # azul primary — la cartera real Lluis
    "shadow": "#8B5CF6",              # violeta — system would-have-done
    "quality": "#10B981",             # verde — Quality factor
    "value": "#F59E0B",               # ámbar — Value factor
    "momentum": "#EC4899",            # rosa — Momentum factor
    "aggressive": "#EF4444",          # rojo — Aggressive (max-Sharpe)
    "conservative": "#14B8A6",        # teal — Conservative (risk parity)
    "benchmark_passive": "#6B7280",   # gris — passive benchmark IWDA/VFEM/IEAG
    "robo_advisor": "#A78BFA",        # lavanda — Indexa replica con fee
    "spy_benchmark": "#FBBF24",       # dorado — SPY índice US
    "indexa_10_benchmark": "#06B6D4", # cyan — Indexa Cartera 10
    "hrp_paper": "#84CC16",           # lima — HRP López de Prado
    "claude_autonomous": "#F97316",   # naranja vibrante — Claude paper trader
}


# ----------------------------------------------------------------------
# Status badge color map
# ----------------------------------------------------------------------
STATUS_BADGE_COLORS: dict[str, str] = {
    "green": SUCCESS_POSITIVE,
    "yellow": WARNING_NEUTRAL,
    "orange": WARNING_NEUTRAL,
    "red": DANGER_LOSS,
    "blue": ACCENT_PRIMARY,
    "neutral": TEXT_SECONDARY,
}

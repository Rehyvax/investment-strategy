"""Generate dashboard/data/cerebro_state.json deterministically.

Phase 2B-1: NO LLM. All narratives derived from rule-based templates
over snapshots + events + theses + price log. Phase 2B-2 will swap
selected narrative blocks for Anthropic API outputs.

CLI:
  python scripts/generate_cerebro_state.py [--date YYYY-MM-DD]
                                           [--out path]
                                           [--dry-run]

Sources consumed:
  data/snapshots/{portfolio}/*.json     (rebuilder output, NAV authority)
  data/events/portfolios/{pid}/trades.jsonl
  data/events/theses/*.jsonl            (recommendation + override)
  data/events/prices/YYYY-MM.jsonl      (FX + market proxies)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.portfolios.price_log import PriceLog  # noqa: E402
from llm_narratives import (  # noqa: E402
    generate_comparative_narrative,
    generate_market_state_narrative,
    is_llm_available,
    refine_recommendation_narrative,
)


def _load_env_file() -> None:
    """Load .env into the process environment. Called from `main()` —
    NOT at import time — so importing this module never triggers a
    live LLM path during tests."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
TRADES_DIR = ROOT / "data" / "events" / "portfolios"
THESES_DIR = ROOT / "data" / "events" / "theses"
DEFAULT_OUT = ROOT / "dashboard" / "data" / "cerebro_state.json"

ALL_PORTFOLIOS = (
    "real",
    "shadow",
    "quality",
    "value",
    "momentum",
    "aggressive",
    "conservative",
    "benchmark_passive",
    "robo_advisor",
)

INSTITUTIONAL_PALETTE = {
    "real": "#1E40AF",
    "shadow": "#0891B2",
    "quality": "#15803D",
    "value": "#B91C1C",
    "momentum": "#A16207",
    "aggressive": "#6D28D9",
    "conservative": "#0F766E",
    "benchmark_passive": "#64748B",
    "robo_advisor": "#475569",
}

DEFAULT_VISIBLE = {"real", "benchmark_passive"}


# ----------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------
def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_snapshot(portfolio_id: str, on: date) -> dict | None:
    """Loads the snapshot on `on` (exact) or the most recent <= `on`."""
    pdir = SNAPSHOTS_DIR / portfolio_id
    if not pdir.exists():
        return None
    target = on.isoformat()
    candidates: list[tuple[str, Path]] = []
    for f in pdir.glob("*.json"):
        # Skip _proposal/_screening files.
        if f.name.startswith("_"):
            continue
        stem = f.stem
        # Require YYYY-MM-DD stem.
        if len(stem) != 10 or stem[4] != "-" or stem[7] != "-":
            continue
        if stem <= target:
            candidates.append((stem, f))
    if not candidates:
        return None
    candidates.sort()
    with candidates[-1][1].open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _list_snapshot_dates(portfolio_id: str) -> list[str]:
    pdir = SNAPSHOTS_DIR / portfolio_id
    if not pdir.exists():
        return []
    out: list[str] = []
    for f in pdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            out.append(stem)
    return sorted(out)


# ----------------------------------------------------------------------
# Block A — Market state (price-log driven heuristics, no LLM)
# ----------------------------------------------------------------------
def generate_market_state(as_of: date) -> dict[str, Any]:
    """Pure rule-based regime classifier. VIX read from the price log
    if available, else placeholder. No yfinance calls at generation
    time (the price log is the deterministic source of truth)."""
    pl = PriceLog()
    vix_rec = pl.get_price("^VIX", as_of)
    vix: float | None = vix_rec.close if vix_rec else None

    # Classify regime from VIX (literature-grounded crude buckets).
    if vix is None:
        regime, color, fear_level = "neutral", "neutral", "unknown"
    elif vix < 15:
        regime, color, fear_level = "risk_on_moderate", "green", "low"
    elif vix < 20:
        regime, color, fear_level = "neutral", "yellow", "moderate"
    elif vix < 30:
        regime, color, fear_level = "risk_off_moderate", "orange", "elevated"
    else:
        regime, color, fear_level = "risk_off_strong", "red", "high"

    # Money-flow heuristic — read XLK vs XLU proxy from log if present.
    xlk = pl.get_price("XLK", as_of)
    xlu = pl.get_price("XLU", as_of)
    if xlk and xlu and xlk.close > 0 and xlu.close > 0:
        # Use ratio at as_of as a directional, not absolute, signal.
        ratio = xlk.close / xlu.close
        if ratio > 3.5:
            money_flow = (
                "Capital favorece tecnología sobre defensivos "
                "(ratio XLK/XLU elevado)."
            )
        elif ratio < 2.5:
            money_flow = (
                "Capital rotando a defensivos / utilities "
                "(ratio XLK/XLU bajo)."
            )
        else:
            money_flow = "Sin sesgo sectorial claro tecno vs defensivo."
    else:
        money_flow = (
            "Sin datos de flujo sectorial en el price log. "
            "Backfill XLK / XLU para activar el indicador."
        )

    # Bond / equity ratio — use SPY vs TLT if available as proxy.
    spy_now = pl.get_price("SPY", as_of)
    tlt_now = pl.get_price("TLT", as_of)
    spy_30d = pl.get_price("SPY", date.fromordinal(as_of.toordinal() - 30))
    tlt_30d = pl.get_price("TLT", date.fromordinal(as_of.toordinal() - 30))
    bond_equity_ratio_30d = 0.0
    if all(x is not None for x in (spy_now, tlt_now, spy_30d, tlt_30d)):
        spy_ret = (spy_now.close / spy_30d.close) - 1
        tlt_ret = (tlt_now.close / tlt_30d.close) - 1
        bond_equity_ratio_30d = tlt_ret - spy_ret

    vix_str = f"{vix:.1f}" if vix is not None else "—"
    explanation_template = {
        "risk_on_moderate": (
            "Risk-on moderado. VIX {vix} en zona calmada; "
            "sin signos materiales de estrés."
        ),
        "neutral": (
            "Mercado en transición. VIX {vix} sin señal direccional "
            "fuerte; observar próximos catalizadores macro."
        ),
        "risk_off_moderate": (
            "Cautela en mercado. VIX {vix} elevado; ajustar exposure "
            "a equity en relación a tu tolerancia personal al riesgo."
        ),
        "risk_off_strong": (
            "Estrés material en mercado. VIX {vix} alto; revisar "
            "concentración y considerar el cash como activo estratégico."
        ),
    }
    explanation = explanation_template.get(
        regime, "Sin datos suficientes para clasificar el régimen."
    ).format(vix=vix_str)

    if vix is None:
        fear_summary = (
            "VIX no presente en el price log. Backfill ^VIX para "
            "activar la clasificación de régimen."
        )
    else:
        fear_summary = (
            f"VIX {vix:.2f}. Bond/Equity 30d ratio "
            f"{bond_equity_ratio_30d * 100:+.1f}%."
        )

    state: dict[str, Any] = {
        "regime": regime,
        "regime_color": color,
        "explanation": explanation,
        "money_flow": money_flow,
        "fear_level": fear_level,
        "vix": vix if vix is not None else 0.0,
        "bond_equity_ratio_30d": bond_equity_ratio_30d,
        "fear_summary": fear_summary,
        "_narrative_source": "rule_based",
    }

    # LLM enrichment: try to upgrade the explanation with a Sonnet
    # narrative. Falls back silently to the deterministic text if the
    # API is unavailable or errors out.
    if is_llm_available():
        portfolio_ctx = generate_portfolio_real(as_of)
        llm_text = generate_market_state_narrative(state, portfolio_ctx)
        if llm_text:
            state["explanation"] = llm_text
            state["_narrative_source"] = "llm"

    return state


# ----------------------------------------------------------------------
# Block B — Portfolio real summary
# ----------------------------------------------------------------------
def _nav_on(portfolio_id: str, on: date) -> float | None:
    s = _load_snapshot(portfolio_id, on)
    if s is None:
        return None
    return float(s.get("nav_total_eur", 0.0))


def _delta_pct(now: float | None, ref: float | None) -> float | None:
    if now is None or ref is None or ref == 0:
        return None
    return (now / ref - 1.0) * 100.0


def _position_weight(p: dict, nav_total_eur: float) -> float:
    """Returns weight_pct from the position. Falls back to
    current_value_eur / NAV when weight_pct is missing (rebuilder v1
    snapshots do not emit weight_pct)."""
    w = p.get("weight_pct")
    if isinstance(w, (int, float)) and w > 0:
        return float(w)
    cv = p.get("current_value_eur")
    if isinstance(cv, (int, float)) and nav_total_eur > 0:
        return float(cv) / nav_total_eur * 100.0
    return 0.0


def _health_status(
    positions: list[dict], nav_total_eur: float = 0.0
) -> tuple[str, str]:
    """Return (status, summary). Single-position concentration is the
    only check we can compute reliably from rebuilder snapshots (sector
    / country are not propagated by `SnapshotRebuilder`). When that
    metadata is enriched later, this function expands automatically."""
    if not positions:
        return "green", "Cartera 100% cash. Sin breaches estructurales."

    weights = [_position_weight(p, nav_total_eur) for p in positions]
    max_w = max(weights) if weights else 0.0

    # Sector / country only counted when at least one position carries
    # the metadata. Avoids false 'Unknown' sector breaches.
    have_sector = any(
        p.get("sector_at_purchase") or p.get("sector") for p in positions
    )
    have_country = any(
        p.get("country_at_purchase") or p.get("country") for p in positions
    )
    max_sector: float | None = None
    max_country: float | None = None
    if have_sector:
        sectors: dict[str, float] = {}
        for p in positions:
            sec = p.get("sector_at_purchase") or p.get("sector")
            if not sec:
                continue
            sectors[sec] = sectors.get(sec, 0.0) + _position_weight(
                p, nav_total_eur
            )
        max_sector = max(sectors.values()) if sectors else None
    if have_country:
        countries: dict[str, float] = {}
        for p in positions:
            c = p.get("country_at_purchase") or p.get("country")
            if not c:
                continue
            countries[c] = countries.get(c, 0.0) + _position_weight(
                p, nav_total_eur
            )
        max_country = max(countries.values()) if countries else None

    SINGLE_CAP, SECTOR_CAP, COUNTRY_CAP = 12.0, 35.0, 80.0
    breaches: list[str] = []
    if max_w > SINGLE_CAP:
        breaches.append(f"single {max_w:.1f}%>{SINGLE_CAP}%")
    if max_sector is not None and max_sector > SECTOR_CAP:
        breaches.append(f"sector {max_sector:.1f}%>{SECTOR_CAP}%")
    if max_country is not None and max_country > COUNTRY_CAP:
        breaches.append(f"country {max_country:.1f}%>{COUNTRY_CAP}%")
    if breaches:
        return "red", "Breach de caps: " + ", ".join(breaches)
    near: list[str] = []
    if max_w > SINGLE_CAP * 0.85:
        near.append(f"single {max_w:.1f}%")
    if max_sector is not None and max_sector > SECTOR_CAP * 0.85:
        near.append(f"sector {max_sector:.1f}%")
    if near:
        return "yellow", "Concentración cercana a cap: " + ", ".join(near)

    summary_parts = [f"Max single {max_w:.1f}%"]
    if max_sector is not None:
        summary_parts.append(f"max sector {max_sector:.1f}%")
    if max_country is not None:
        summary_parts.append(f"max country {max_country:.1f}%")
    return (
        "green",
        "Sin breaches estructurales. " + ", ".join(summary_parts) + ".",
    )


def generate_portfolio_real(as_of: date) -> dict[str, Any]:
    snap = _load_snapshot("real", as_of)
    if snap is None:
        return {
            "nav_total_eur": 0.0,
            "nav_delta_1d_pct": 0.0,
            "nav_delta_1w_pct": 0.0,
            "nav_delta_1m_pct": 0.0,
            "nav_delta_ytd_pct": 0.0,
            "health_status": "neutral",
            "health_summary": "Sin snapshot real disponible.",
            "drawdown_current_pct": 0.0,
            "drawdown_from_peak": as_of.isoformat(),
            "cash_eur": 0.0,
            "cash_pct_nav": 0.0,
            "positions_count": 0,
        }

    nav_now = float(snap.get("nav_total_eur", 0.0))
    cash_now = float(snap.get("cash_eur", 0.0))
    positions = snap.get("positions", []) or []
    nav_1d = _nav_on("real", date.fromordinal(as_of.toordinal() - 1))
    nav_7d = _nav_on("real", date.fromordinal(as_of.toordinal() - 7))
    nav_30d = _nav_on("real", date.fromordinal(as_of.toordinal() - 30))
    nav_ytd = _nav_on("real", date(as_of.year, 1, 2))

    # Drawdown — compare to peak across all available snapshots.
    peak_nav = nav_now
    peak_date = as_of.isoformat()
    for d_str in _list_snapshot_dates("real"):
        d = date.fromisoformat(d_str)
        if d > as_of:
            continue
        nav = _nav_on("real", d)
        if nav is not None and nav > peak_nav:
            peak_nav = nav
            peak_date = d_str
    drawdown_pct = (
        ((nav_now / peak_nav) - 1.0) * 100.0 if peak_nav > 0 else 0.0
    )

    health_status, health_summary = _health_status(positions, nav_now)

    return {
        "nav_total_eur": round(nav_now, 2),
        "nav_delta_1d_pct": round(_delta_pct(nav_now, nav_1d) or 0.0, 2),
        "nav_delta_1w_pct": round(_delta_pct(nav_now, nav_7d) or 0.0, 2),
        "nav_delta_1m_pct": round(_delta_pct(nav_now, nav_30d) or 0.0, 2),
        "nav_delta_ytd_pct": round(_delta_pct(nav_now, nav_ytd) or 0.0, 2),
        "health_status": health_status,
        "health_summary": health_summary,
        "drawdown_current_pct": round(drawdown_pct, 2),
        "drawdown_from_peak": peak_date,
        "cash_eur": round(cash_now, 2),
        "cash_pct_nav": round(
            (cash_now / nav_now * 100.0) if nav_now > 0 else 0.0, 1
        ),
        "positions_count": len(positions),
    }


# ----------------------------------------------------------------------
# Block B' — Tax alerts (2-month rule, art. 33.5 LIRPF)
# ----------------------------------------------------------------------
def generate_tax_alerts(as_of: date) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    real_trades = TRADES_DIR / "real" / "trades.jsonl"
    for event in _iter_jsonl(real_trades):
        if event.get("side") != "sell":
            continue
        if not event.get("is_loss"):
            continue
        window_end_str = event.get("two_month_rule_window_end")
        if not window_end_str:
            continue
        try:
            window_end = date.fromisoformat(window_end_str)
        except ValueError:
            continue
        if window_end < as_of:
            continue
        loss_eur = abs(float(event.get("realized_pnl_eur", 0.0)))
        ticker = event.get("ticker", "?")
        trade_date = event.get("trade_date", "—")
        alerts.append(
            {
                "asset": ticker,
                "alert_type": "2_month_rule",
                "message": (
                    f"NO recomprar {ticker} antes de {window_end_str} para "
                    f"no perder la deducción de €{loss_eur:.2f} "
                    f"(loss harvested {trade_date})."
                ),
                "expires": window_end_str,
            }
        )
    return alerts


# ----------------------------------------------------------------------
# Block C — Multi-portfolio chart data (normalized base-100)
# ----------------------------------------------------------------------
def generate_portfolios_chart_data(as_of: date) -> dict[str, Any]:
    # Collect the union of snapshot dates across all portfolios, capped
    # at as_of_date, sorted ascending.
    all_dates: set[str] = set()
    for pid in ALL_PORTFOLIOS:
        for d in _list_snapshot_dates(pid):
            if d <= as_of.isoformat():
                all_dates.add(d)
    labels = sorted(all_dates)

    series: list[dict[str, Any]] = []
    for pid in ALL_PORTFOLIOS:
        pdates = _list_snapshot_dates(pid)
        if not pdates:
            continue
        base_date = pdates[0]
        base_nav = _nav_on(pid, date.fromisoformat(base_date))
        if not base_nav:
            continue
        values: list[float] = []
        last_known = 100.0
        for lbl in labels:
            nav = _nav_on(pid, date.fromisoformat(lbl))
            if nav is None:
                values.append(last_known)
            else:
                idx = nav / base_nav * 100.0
                last_known = idx
                values.append(round(idx, 2))
        series.append(
            {
                "name": pid,
                "values": values,
                "color": INSTITUTIONAL_PALETTE.get(pid, "#64748B"),
                "default_visible": pid in DEFAULT_VISIBLE,
            }
        )
    return {"labels": labels, "series": series}


# ----------------------------------------------------------------------
# Block D — Recommendations (driven by theses + override annotations)
# ----------------------------------------------------------------------
def _load_thesis_chain(ticker: str) -> tuple[dict | None, dict | None]:
    """Returns (latest_thesis, override_annotation) for the ticker.
    Returns (None, None) when a `thesis_closed_position` event has been
    recorded — closed positions are terminal for recommendation purposes
    even though the historical events remain in the audit trail."""
    path = THESES_DIR / f"{ticker}.jsonl"
    if not path.exists():
        return None, None
    latest_thesis: dict | None = None
    override: dict | None = None
    closed = False
    for event in _iter_jsonl(path):
        et = event.get("event_type")
        if et == "thesis":
            latest_thesis = event
        elif et == "thesis_user_override_annotation":
            override = event
        elif et == "thesis_closed_position":
            closed = True
    if closed:
        return None, None
    return latest_thesis, override


def _real_position_weight(ticker: str, as_of: date) -> float:
    snap = _load_snapshot("real", as_of)
    if not snap:
        return 0.0
    nav = float(snap.get("nav_total_eur", 0.0))
    for p in snap.get("positions", []) or []:
        if p.get("ticker") == ticker:
            return _position_weight(p, nav)
    return 0.0


def _recommendation_for(
    ticker: str, as_of: date
) -> dict[str, Any] | None:
    thesis, override = _load_thesis_chain(ticker)
    if thesis is None:
        return None
    rec_field = (
        thesis.get("recommendation")
        or thesis.get("recommendation_v2")
        or "watch"
    ).lower()
    conf = thesis.get("confidence_calibrated")
    weight = _real_position_weight(ticker, as_of)

    # Map thesis recommendation -> dashboard action type + color.
    if override and override.get("user_override_active"):
        rec_type = "HOLD_OVERRIDE"
        priority = "high"
        color = "orange"
        headline = (
            f"{ticker}: override activo, recordatorio gate Q2"
        )
        note = override.get("note", "")
        narrative = (
            "El sistema recomienda salir; mantienes la posición de "
            "forma consciente. "
            + (note[:280] + "…" if len(note) > 280 else note)
        )
        action = (
            "Override consciente activo. Próximo gate: Q2 2026. "
            "Monitor automatic via news-scanner cuando esté operativo."
        )
    elif rec_field == "exit" or rec_field == "sell":
        rec_type, color, priority = "EXIT", "red", "high"
        headline = f"{ticker}: tesis recomienda salir"
        narrative = (
            f"La tesis vigente recomienda EXIT con confianza "
            f"{conf or '—'}. Considerar reducir / cerrar la posición "
            f"o registrar un override consciente si discrepas."
        )
        action = "Reducir o cerrar posición. Si discrepas, registrar override."
    elif rec_field == "reduce":
        rec_type, color, priority = "REDUCE", "yellow", "medium"
        headline = f"{ticker}: tesis sugiere reducir exposición"
        narrative = (
            "La tesis sugiere reducir el peso de la posición sin "
            "necesariamente cerrarla. Revisar concentración y "
            "alternativas con mejor risk/reward."
        )
        action = "Reducir peso al rango sugerido por la tesis."
    elif rec_field == "watch":
        # Watch with falsifier in motion → WATCH; else HOLD.
        falsifier_audit = thesis.get("falsifier_status_audit", "")
        falsifier_in_motion = False
        if isinstance(falsifier_audit, str):
            falsifier_in_motion = any(
                kw in falsifier_audit.lower()
                for kw in ("halfway", "partial", "below threshold", "missed")
            )
        elif isinstance(falsifier_audit, dict):
            # Scan the values for any status indicating partial activation.
            for fdef in falsifier_audit.values():
                if isinstance(fdef, dict):
                    status = str(fdef.get("status", "")).lower()
                    if any(
                        kw in status
                        for kw in (
                            "halfway",
                            "partial",
                            "activated",
                            "in_motion",
                        )
                    ):
                        falsifier_in_motion = True
                        break
        if falsifier_in_motion:
            rec_type, color, priority = "WATCH", "yellow", "high"
            headline = f"{ticker}: falsifier en marcha, vigilar gate"
        else:
            rec_type, color, priority = "HOLD", "yellow", "medium"
            headline = f"{ticker}: mantener, sin disparadores activos"
        catalysts = thesis.get("catalysts_upcoming", []) or []
        cat_strings: list[str] = []
        for c in catalysts[:2]:
            if isinstance(c, dict):
                txt = (
                    c.get("description")
                    or c.get("name")
                    or c.get("event")
                    or c.get("catalyst")
                    or c.get("title")
                    or ""
                )
                date_str = c.get("expected_date") or c.get("date") or ""
                if txt and date_str:
                    cat_strings.append(f"{txt} ({date_str})")
                elif txt:
                    cat_strings.append(txt)
                elif date_str:
                    cat_strings.append(date_str)
            elif isinstance(c, str):
                cat_strings.append(c)
        cat_str = "; ".join(s for s in cat_strings if s) or "ninguno listado"
        if isinstance(falsifier_audit, str):
            falsifier_summary = (
                falsifier_audit[:200] if falsifier_audit else "—"
            )
        elif isinstance(falsifier_audit, dict):
            # Show count of falsifiers with status notes.
            n = sum(
                1
                for f in falsifier_audit.values()
                if isinstance(f, dict) and f.get("status")
            )
            falsifier_summary = (
                f"{n} falsifiers tracked; "
                + ("alguno en motion." if falsifier_in_motion else "ninguno activado.")
            )
        else:
            falsifier_summary = "—"
        narrative = (
            f"Tesis vigente: WATCH con confianza {conf or '—'}. "
            f"Próximos catalizadores: {cat_str}. "
            f"Falsifier status: {falsifier_summary}"
        )
        action = "Mantener posición y revisar tras el próximo gate."
    elif rec_field in ("buy", "buy_more", "buy_residual"):
        rec_type, color, priority = "BUY", "green", "medium"
        headline = f"{ticker}: tesis recomienda añadir / abrir"
        narrative = (
            f"Tesis recomienda BUY con confianza {conf or '—'}. "
            f"Validar tamaño en función del peso actual ({weight:.1f}% NAV) "
            f"y los caps de concentración."
        )
        action = "Considerar añadir respetando caps de concentración."
    else:
        rec_type, color, priority = "HOLD", "yellow", "low"
        headline = f"{ticker}: HOLD por defecto"
        narrative = (
            "Sin recomendación explícita en la tesis. Posición se "
            "mantiene sin acción salvo cambio de catalizadores."
        )
        action = "Sin acción inmediata."

    return {
        "id": f"rec_{ticker.lower()}",
        "type": rec_type,
        "asset": ticker,
        "priority": priority,
        "headline": headline,
        "narrative": narrative,
        "action": action,
        "color": color,
        "_weight_pct": weight,
    }


_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _position_data_for(ticker: str, as_of: date) -> dict[str, Any]:
    """Returns the position dict from the real snapshot for `ticker`,
    or an empty dict if not held."""
    snap = _load_snapshot("real", as_of)
    if snap is None:
        return {}
    nav = float(snap.get("nav_total_eur", 0.0))
    for p in snap.get("positions", []) or []:
        if p.get("ticker") == ticker:
            return {
                **p,
                "weight_pct": _position_weight(p, nav),
            }
    return {}


def _llm_context_for(
    ticker: str, rec: dict[str, Any]
) -> str:
    """Build a concise context string for the LLM refinement prompt."""
    thesis, override = _load_thesis_chain(ticker)
    parts: list[str] = []
    if thesis:
        rec_field = (
            thesis.get("recommendation")
            or thesis.get("recommendation_v2")
            or "—"
        )
        conf = thesis.get("confidence_calibrated")
        parts.append(f"Tesis: rec={rec_field}, conf={conf}")
        catalysts = thesis.get("catalysts_upcoming", []) or []
        if catalysts:
            cat_str_parts: list[str] = []
            for c in catalysts[:2]:
                if isinstance(c, dict):
                    txt = (
                        c.get("description")
                        or c.get("name")
                        or c.get("event")
                        or ""
                    )
                    d = c.get("expected_date") or c.get("date") or ""
                    if txt or d:
                        cat_str_parts.append(
                            f"{txt} ({d})" if d else txt
                        )
                elif isinstance(c, str):
                    cat_str_parts.append(c)
            if cat_str_parts:
                parts.append("Catalysts: " + "; ".join(cat_str_parts))
    if override and override.get("user_override_active"):
        note = override.get("note", "")
        parts.append(
            "Override usuario activo. " + (note[:300] if note else "")
        )
    return " | ".join(parts) if parts else "Sin contexto adicional."


def generate_recommendations(as_of: date) -> list[dict[str, Any]]:
    if not THESES_DIR.exists():
        return []
    candidates: list[dict[str, Any]] = []
    for path in THESES_DIR.glob("*.jsonl"):
        ticker = path.stem
        rec = _recommendation_for(ticker, as_of)
        if rec is not None:
            candidates.append(rec)
    candidates.sort(
        key=lambda r: (
            _PRIORITY_RANK.get(r["priority"], 99),
            -r.get("_weight_pct", 0.0),
        )
    )

    out: list[dict[str, Any]] = []
    llm_on = is_llm_available()
    for c in candidates[:3]:
        clean = {k: v for k, v in c.items() if not k.startswith("_")}
        # Default tag — overwritten on LLM success.
        clean["_narrative_source"] = "rule_based"
        if llm_on:
            position_data = _position_data_for(clean["asset"], as_of)
            context = _llm_context_for(clean["asset"], clean)
            llm_text = refine_recommendation_narrative(
                clean, position_data, context
            )
            if llm_text:
                clean["narrative"] = llm_text
                clean["_narrative_source"] = "llm"
        out.append(clean)
    return out


# ----------------------------------------------------------------------
# Block E — Comparative analysis (rotating comparator)
# ----------------------------------------------------------------------
_COMPARATOR_REASONS = {
    "shadow": (
        "Shadow expone tu cartera real saneada como upper bound de "
        "tu propio stock picking."
    ),
    "benchmark_passive": (
        "Benchmark passive (70% IWDA / 20% VFEM / 10% IEAG) es la "
        "alternativa indexada barata; mide tu skill neta de fees."
    ),
    "robo_advisor": (
        "Robo-advisor replica un Indexa agresivo con 0.40% AuM fee; "
        "mide si tu skill bate el coste del asesor."
    ),
}


def generate_comparative(as_of: date) -> dict[str, Any]:
    real_dates = _list_snapshot_dates("real")
    if not real_dates:
        return {
            "headline": "Sin datos suficientes",
            "narrative": "Genera al menos un snapshot real para activar comparativa.",
            "comparator_today": "benchmark_passive",
            "comparator_reason": _COMPARATOR_REASONS["benchmark_passive"],
            "action": "—",
        }
    t0 = date.fromisoformat(real_dates[0])
    nav_real_t0 = _nav_on("real", t0)
    nav_real_now = _nav_on("real", as_of)
    delta_real = _delta_pct(nav_real_now, nav_real_t0) or 0.0

    candidates = ["shadow", "benchmark_passive", "robo_advisor"]
    comparator = candidates[as_of.toordinal() % len(candidates)]
    comp_t0 = _nav_on(comparator, t0)
    comp_now = _nav_on(comparator, as_of)
    delta_comp = _delta_pct(comp_now, comp_t0) if comp_now and comp_t0 else None

    if delta_comp is None:
        headline = f"Comparativa vs {comparator} no disponible"
        narrative = (
            f"Tu real ha rendido {delta_real:+.2f}% desde T0. "
            f"No hay snapshots suficientes de {comparator} para comparar."
        )
        action = "Espera a tener al menos un snapshot común con el comparador."
    else:
        diff = delta_real - delta_comp
        if diff > 0.5:
            headline = "Tu skill está aportando"
        elif diff < -0.5:
            headline = f"Underperform vs {comparator}"
        else:
            headline = "Vas en línea, diferencia es ruido en horizonte corto"
        narrative = (
            f"Tu real ha rendido {delta_real:+.2f}% desde T0. "
            f"{comparator} ha rendido {delta_comp:+.2f}%. "
            f"Diferencia: {diff:+.2f} pp."
        )
        if abs(diff) < 0.5:
            action = "No cambies nada hoy. Diferencia es ruido en horizonte corto."
        elif diff > 0:
            action = (
                "Mantén el proceso. Reevaluar diferencia en >30 días "
                "(Brinson-Fachler) cuando esté disponible."
            )
        else:
            action = (
                f"Subir watch sobre {comparator}: evaluar si la diferencia "
                "persiste a 30 días para conclusiones."
            )
    result: dict[str, Any] = {
        "headline": headline,
        "narrative": narrative,
        "comparator_today": comparator,
        "comparator_reason": _COMPARATOR_REASONS[comparator],
        "action": action,
        "_narrative_source": "rule_based",
    }

    if is_llm_available() and delta_comp is not None:
        nav_shadow_now = _nav_on("shadow", as_of)
        nav_shadow_t0 = _nav_on("shadow", t0)
        nav_bench_now = _nav_on("benchmark_passive", as_of)
        nav_bench_t0 = _nav_on("benchmark_passive", t0)
        nav_robo_now = _nav_on("robo_advisor", as_of)
        nav_robo_t0 = _nav_on("robo_advisor", t0)
        llm_payload = {
            "nav_real": nav_real_now or 0,
            "delta_real_pct": delta_real,
            "nav_shadow": nav_shadow_now or 0,
            "delta_shadow_pct": _delta_pct(nav_shadow_now, nav_shadow_t0) or 0.0,
            "nav_benchmark": nav_bench_now or 0,
            "delta_benchmark_pct": _delta_pct(nav_bench_now, nav_bench_t0) or 0.0,
            "nav_robo": nav_robo_now or 0,
            "delta_robo_pct": _delta_pct(nav_robo_now, nav_robo_t0) or 0.0,
            "comparator_today": comparator,
            "diff_pp": delta_real - delta_comp,
        }
        llm_out = generate_comparative_narrative(llm_payload)
        if llm_out:
            result["headline"] = llm_out["headline"]
            result["narrative"] = llm_out["narrative"]
            result["_narrative_source"] = "llm"

    return result


# ----------------------------------------------------------------------
# Block F — News feed (empty until news-scanner is operational)
# ----------------------------------------------------------------------
def generate_news_feed(as_of: date) -> list[dict[str, Any]]:
    return []


# ----------------------------------------------------------------------
# Upcoming events per asset (yfinance calendar + dividends, 2-month rule,
# thesis falsifier check dates). Consumed by Pantalla 3 Detalle.
# ----------------------------------------------------------------------
def _get_upcoming_events_for_asset(
    ticker: str, as_of: date
) -> list[dict[str, str]]:
    """Returns up to 5 dated future events derived from real sources.
    Never hardcoded. Sources tagged in `source` field of each event.

    Sources:
      - yfinance: next earnings + estimated ex-dividend
      - real trades: 2-month rule LIRPF expirations
      - thesis: gate / next_check / next_evaluation_trigger dates
    """
    import re

    events: list[dict[str, str]] = []
    as_of_str = as_of.isoformat()

    # --- yfinance earnings + estimated ex-dividend -------------------
    try:
        import yfinance as yf
        import pandas as pd

        try:
            t = yf.Ticker(ticker)
        except Exception:
            t = None
        if t is not None:
            # Earnings
            try:
                cal = t.calendar
                earnings_date = None
                if cal is not None:
                    if (
                        hasattr(cal, "columns")
                        and "Earnings Date" in getattr(cal, "columns", [])
                    ):
                        earnings_date = cal["Earnings Date"].iloc[0]
                    elif isinstance(cal, dict) and "Earnings Date" in cal:
                        ed = cal["Earnings Date"]
                        earnings_date = ed[0] if isinstance(ed, list) else ed
                if earnings_date is not None:
                    ts = pd.Timestamp(earnings_date)
                    if ts.date() > as_of:
                        events.append(
                            {
                                "date": ts.strftime("%Y-%m-%d"),
                                "event": "Próximo earnings",
                                "type": "earnings",
                                "source": "yfinance_calendar",
                            }
                        )
            except Exception:
                pass

            # Ex-dividend estimate from recurring frequency
            try:
                divs = t.dividends
                if divs is not None and not divs.empty and len(divs) >= 2:
                    last_div_date = divs.index[-1]
                    gap_days = (
                        last_div_date - divs.index[-2]
                    ).days or 91
                    estimated_next = last_div_date + pd.Timedelta(
                        days=gap_days
                    )
                    if estimated_next.date() > as_of:
                        events.append(
                            {
                                "date": estimated_next.strftime("%Y-%m-%d"),
                                "event": (
                                    f"Ex-dividend estimado "
                                    f"(último {float(divs.iloc[-1]):.2f})"
                                ),
                                "type": "dividend_estimated",
                                "source": "yfinance_estimate",
                            }
                        )
            except Exception:
                pass
    except ImportError:
        pass

    # --- 2-month rule LIRPF from realized losses ---------------------
    trades_path = TRADES_DIR / "real" / "trades.jsonl"
    for tr in _iter_jsonl(trades_path):
        if tr.get("ticker") != ticker:
            continue
        if tr.get("side") != "sell" or not tr.get("is_loss"):
            continue
        end = tr.get("two_month_rule_window_end")
        if isinstance(end, str) and end > as_of_str:
            events.append(
                {
                    "date": end,
                    "event": (
                        "Fin 2-month rule LIRPF (puedes recomprar sin "
                        "perder la deducción)"
                    ),
                    "type": "tax_rule",
                    "source": "trades_log",
                }
            )

    # --- Thesis gates / falsifier check dates ------------------------
    thesis_path = THESES_DIR / f"{ticker}.jsonl"
    if thesis_path.exists():
        thesis = None
        for v in reversed(list(_iter_jsonl(thesis_path))):
            if v.get("event_type") in ("thesis", "thesis_review"):
                thesis = v
                break
        if thesis is not None:
            fsa = thesis.get("falsifier_status_audit", {})
            if isinstance(fsa, dict):
                for name, det in fsa.items():
                    if not isinstance(det, dict):
                        continue
                    nxt = det.get("next_check_date") or det.get(
                        "next_gate_date"
                    )
                    if isinstance(nxt, str) and nxt > as_of_str:
                        events.append(
                            {
                                "date": nxt,
                                "event": f"Check falsifier: {name}",
                                "type": "thesis_gate",
                                "source": "thesis",
                            }
                        )
            for fld in (
                "next_evaluation_trigger",
                "next_review",
                "next_evaluation_date",
            ):
                v = thesis.get(fld)
                if isinstance(v, str):
                    m = re.search(r"\d{4}-\d{2}-\d{2}", v)
                    if m and m.group() > as_of_str:
                        events.append(
                            {
                                "date": m.group(),
                                "event": "Re-evaluación de la tesis",
                                "type": "thesis_review",
                                "source": "thesis",
                            }
                        )
                        break
            # Catalysts already structured in the thesis.
            for c in thesis.get("catalysts_upcoming", []) or []:
                if not isinstance(c, dict):
                    continue
                d_str = (
                    c.get("expected_date")
                    or c.get("date")
                    or c.get("when")
                )
                if isinstance(d_str, str):
                    m = re.search(r"\d{4}-\d{2}-\d{2}", d_str)
                    if m and m.group() > as_of_str:
                        label = (
                            c.get("description")
                            or c.get("name")
                            or c.get("event")
                            or c.get("catalyst")
                            or "Catalizador"
                        )
                        events.append(
                            {
                                "date": m.group(),
                                "event": str(label),
                                "type": "thesis_catalyst",
                                "source": "thesis",
                            }
                        )

    # Sort + dedupe by (date, event)
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for e in sorted(events, key=lambda x: x["date"]):
        key = (e["date"], e["event"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out[:5]


def generate_upcoming_events_by_asset(
    as_of: date,
) -> dict[str, list[dict[str, str]]]:
    """Per-ticker upcoming events for the dashboard's Pantalla 3."""
    out: dict[str, list[dict[str, str]]] = {}
    snap = _load_snapshot("real", as_of)
    tickers: set[str] = set()
    if snap:
        for p in snap.get("positions", []) or []:
            t = p.get("ticker")
            if isinstance(t, str):
                tickers.add(t)
    # Also include any ticker with an OPEN thesis even if not currently
    # held (wind-down case). Skip tickers whose thesis has been marked
    # `thesis_closed_position` — these no longer require monitoring.
    if THESES_DIR.exists():
        for f in THESES_DIR.glob("*.jsonl"):
            ticker = f.stem
            has_close = any(
                ev.get("event_type") == "thesis_closed_position"
                for ev in _iter_jsonl(f)
            )
            if not has_close:
                tickers.add(ticker)
    for ticker in sorted(tickers):
        events = _get_upcoming_events_for_asset(ticker, as_of)
        if events:
            out[ticker] = events
    return out


# ----------------------------------------------------------------------
# Main orchestrator + atomic write
# ----------------------------------------------------------------------
def generate_cerebro_state(as_of: date) -> dict[str, Any]:
    next_eval = datetime.now(timezone.utc) + timedelta(hours=24)
    return {
        "generated_at": _now_iso_utc(),
        "next_evaluation": next_eval.isoformat().replace("+00:00", "Z"),
        "as_of_date": as_of.isoformat(),
        "market_state": generate_market_state(as_of),
        "portfolio_real": generate_portfolio_real(as_of),
        "tax_alerts": generate_tax_alerts(as_of),
        "portfolios_chart_data": generate_portfolios_chart_data(as_of),
        "recommendations": generate_recommendations(as_of),
        "comparative_analysis": generate_comparative(as_of),
        "news_feed": generate_news_feed(as_of),
        "upcoming_events_by_asset": generate_upcoming_events_by_asset(as_of),
    }


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    _load_env_file()
    p = argparse.ArgumentParser(description="Generate cerebro_state.json.")
    p.add_argument("--date", type=str, default=None)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    as_of = (
        date.fromisoformat(args.date) if args.date else date.today()
    )
    state = generate_cerebro_state(as_of)

    if args.dry_run:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0

    _atomic_write(args.out, state)
    print(f"cerebro state written to {args.out}")
    print(
        f"  NAV real: EUR {state['portfolio_real']['nav_total_eur']:,.2f}"
    )
    print(f"  Recommendations: {len(state['recommendations'])}")
    print(f"  Tax alerts: {len(state['tax_alerts'])}")
    print(f"  Portfolios in chart: {len(state['portfolios_chart_data']['series'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

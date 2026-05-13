"""Risk Manager agent — second opinion on a debate-verdict's
suggested action.

Evaluates the proposed action against the portfolio caps from CLAUDE.md
(single 12%, sector 35%, country 80%) and the cash buffer. Output is a
structured JSON decision (`approve` | `reject` | `modify`) plus a
short reasoning paragraph.

Public surface:
    evaluate_action(debate_verdict, portfolio_state, ticker) -> dict | None
    compute_concentrations(snapshot, ticker) -> dict   # pure helper
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from llm_narratives import MODEL, get_client  # noqa: E402

SNAPSHOT_DIR = ROOT / "data" / "snapshots" / "real"

CAP_SINGLE_NAME_PCT = 12.0
CAP_SECTOR_PCT = 35.0
CAP_COUNTRY_PCT = 80.0


RISK_MANAGER_SYSTEM_PROMPT = """You are a Risk Manager in an institutional
trading firm. Your role is to evaluate proposed actions against
portfolio risk constraints.

Rules:
- Independent second opinion — you do NOT advocate for the position.
- Focus on: single-name concentration, sector exposure, country exposure,
  cash buffer, drawdown.
- Output approval, rejection, or a modification suggestion.
- If rejecting, suggest a smaller size or conditional execution.
- Tone: institutional, sober, conservative bias is acceptable."""


RISK_MANAGER_PROMPT_TMPL = """Portfolio context:
- NAV: EUR {nav:,}
- Cash: EUR {cash:,} ({cash_pct:.1f}% NAV)
- Positions: {n_positions}
- Top concentration: {top_position} at {top_pct:.1f}% NAV
- Sector concentrations >10%: {sector_concentrations}
- Country concentrations >20%: {country_concentrations}
- Current drawdown vs peak: {drawdown_pct:.2f}%
- Caps (immutable): single {cap_single:.0f}%, sector {cap_sector:.0f}%, country {cap_country:.0f}%

Proposed action (from Bull/Bear debate verdict):
- Ticker: {ticker}
- Current weight: {current_position_pct:.2f}% NAV
- Suggested action: {suggested_action}
- Verdict: {verdict}
- Confidence: {confidence}
- Reasoning excerpt: {reasoning}

Evaluate this proposed action:
1. Does it respect the concentration caps post-trade?
2. Does it improve or worsen sector/country exposure?
3. Does it preserve the cash buffer adequately?
4. Is the suggested size appropriate given confidence?

Respond with a JSON object on a single line, no markdown fence:
{{"approval":"approve|reject|modify","modification":"<one-sentence change or null>","reasoning":"3-4 sentences","constraint_check":{{"cap_single":"ok|warning|breach","cap_sector":"ok|warning|breach","cash_buffer":"ok|low|critical"}}}}

Then on a NEW LINE provide your reasoning paragraph (3-4 sentences)."""


_VALID_APPROVAL = {"approve", "reject", "modify"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def compute_concentrations(
    snapshot: dict[str, Any], ticker: str
) -> dict[str, Any]:
    """Returns the concentration / cash summary used by both the LLM
    prompt and the constraint_check sanity output. Pure function — no
    I/O — so tests can pass a hand-built snapshot dict."""
    nav = float(snapshot.get("nav_total_eur") or 0.0)
    cash = float(snapshot.get("cash_eur") or 0.0)
    positions = snapshot.get("positions") or []

    sectors: dict[str, float] = {}
    countries: dict[str, float] = {}
    top_position = ""
    top_pct = 0.0
    current_position_pct = 0.0

    for p in positions:
        weight = p.get("weight_pct")
        if weight is None and nav > 0:
            cv = float(p.get("current_value_eur") or 0.0)
            weight = (cv / nav) * 100.0
        weight = float(weight or 0.0)
        if weight > top_pct:
            top_pct = weight
            top_position = p.get("ticker", "")
        if p.get("ticker") == ticker:
            current_position_pct = weight
        sec = (p.get("sector_at_purchase") or p.get("sector") or "Unknown")
        ctr = (p.get("country_at_purchase") or p.get("country") or "Unknown")
        sectors[sec] = sectors.get(sec, 0.0) + weight
        countries[ctr] = countries.get(ctr, 0.0) + weight

    return {
        "nav": nav,
        "cash": cash,
        "cash_pct": (cash / nav * 100.0) if nav > 0 else 0.0,
        "n_positions": len(positions),
        "top_position": top_position,
        "top_pct": top_pct,
        "sector_concentrations": {
            s: round(p, 1) for s, p in sectors.items() if p > 10
        },
        "country_concentrations": {
            c: round(p, 1) for c, p in countries.items() if p > 20
        },
        "current_position_pct": current_position_pct,
    }


def parse_risk_response(text: str) -> dict[str, Any]:
    """Defensive parser for the LLM's structured response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    json_line, _, rest = cleaned.partition("\n")
    json_line = json_line.strip()
    if json_line.startswith("```"):
        json_line = json_line.strip("`").strip()
    try:
        parsed = json.loads(json_line)
    except json.JSONDecodeError:
        return {
            "approval": "modify",
            "modification": "manual_review_required",
            "reasoning": cleaned,
            "constraint_check": {
                "cap_single": "warning",
                "cap_sector": "warning",
                "cash_buffer": "warning",
            },
            "_parse_error": "json_decode_failed",
        }
    out: dict[str, Any] = {
        "approval": (
            parsed.get("approval")
            if parsed.get("approval") in _VALID_APPROVAL
            else "modify"
        ),
        "modification": parsed.get("modification"),
        "reasoning": rest.strip() or parsed.get("reasoning", ""),
        "constraint_check": parsed.get("constraint_check") or {},
    }
    return out


def _load_latest_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT_DIR.exists():
        return None
    cands: list[Path] = []
    for f in SNAPSHOT_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        stem = f.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            cands.append(f)
    if not cands:
        return None
    cands.sort()
    return json.loads(cands[-1].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Public LLM-backed entry point
# ---------------------------------------------------------------------------
def evaluate_action(
    debate_verdict: dict[str, Any],
    portfolio_state: dict[str, Any],
    ticker: str,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run the Risk Manager LLM evaluation. `portfolio_state` is the
    `state['portfolio_real']` block from the cerebro state (used for
    drawdown). When `snapshot` is None, the latest real snapshot is
    loaded from disk."""
    client = get_client()
    if client is None:
        return None
    snap = snapshot if snapshot is not None else _load_latest_snapshot()
    if snap is None:
        return None
    conc = compute_concentrations(snap, ticker)

    prompt = RISK_MANAGER_PROMPT_TMPL.format(
        nav=int(conc["nav"]),
        cash=int(conc["cash"]),
        cash_pct=conc["cash_pct"],
        n_positions=conc["n_positions"],
        top_position=conc["top_position"] or "—",
        top_pct=conc["top_pct"],
        sector_concentrations=json.dumps(conc["sector_concentrations"]),
        country_concentrations=json.dumps(conc["country_concentrations"]),
        drawdown_pct=float(portfolio_state.get("drawdown_current_pct") or 0.0),
        cap_single=CAP_SINGLE_NAME_PCT,
        cap_sector=CAP_SECTOR_PCT,
        cap_country=CAP_COUNTRY_PCT,
        ticker=ticker,
        suggested_action=debate_verdict.get("suggested_action", "maintain"),
        verdict=debate_verdict.get("verdict", "thesis_neutral"),
        confidence=debate_verdict.get("confidence", "low"),
        reasoning=(debate_verdict.get("reasoning") or "")[:300],
        current_position_pct=conc["current_position_pct"],
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=RISK_MANAGER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        if not text:
            return None
        result = parse_risk_response(text)
        result["concentrations"] = conc
        return result
    except Exception as exc:  # noqa: BLE001
        print(f"Risk manager error for {ticker}: {exc}")
        return None

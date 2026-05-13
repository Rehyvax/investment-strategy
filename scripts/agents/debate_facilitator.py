"""Debate Facilitator — synthesizes a Bull vs Bear transcript into a
single structured verdict.

Output schema (`facilitate_debate` returns one of these dicts or None):

    {
      "verdict": "thesis_strengthened" | "thesis_neutral" |
                 "thesis_weakened"     | "thesis_invalidated",
      "weight":  "bull_wins" | "bear_wins" | "balanced",
      "key_evidence_for_verdict": "...",
      "key_trigger_to_monitor":    "...",
      "suggested_action":          "maintain | reduce | exit | monitor_X",
      "confidence":                "high | medium | low",
      "reasoning":                 "<4-6 sentence justification>"
    }

The facilitator parses the LLM's first-line JSON; subsequent text is
captured into `reasoning`. Defensive parsing handles markdown fences.
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


FACILITATOR_SYSTEM_PROMPT = """You are a Debate Facilitator synthesizing a
Bull vs Bear research debate on a specific stock position. Your role is
judicial — NOT advocate.

Rules:
- Read the full debate transcript.
- Identify which side carries more weight given the EVIDENCE
  (not rhetorical force).
- Issue a verdict from this fixed enum:
    thesis_strengthened | thesis_neutral | thesis_weakened |
    thesis_invalidated
- Justify in 4-6 sentences with specific evidence references.
- Identify ONE key falsifier or trigger to monitor going forward.
- Suggest concrete action: maintain | reduce | exit | monitor_specific_metric
- Tone: institutional, sober, neutral."""


FACILITATOR_PROMPT_TMPL = """Position: {ticker}

Bull's opening argument:
\"\"\"
{bull_initial}
\"\"\"

Bear's opening argument:
\"\"\"
{bear_initial}
\"\"\"
{additional_rounds}

Issue your verdict in JSON on a single line, no markdown fence:
{{"verdict":"thesis_strengthened|thesis_neutral|thesis_weakened|thesis_invalidated","weight":"bull_wins|bear_wins|balanced","key_evidence_for_verdict":"...","key_trigger_to_monitor":"...","suggested_action":"maintain|reduce|exit|monitor_<metric>","confidence":"high|medium|low"}}

Then on a NEW LINE provide your reasoning (4-6 sentences) without JSON."""


_VALID_VERDICTS = {
    "thesis_strengthened",
    "thesis_neutral",
    "thesis_weakened",
    "thesis_invalidated",
}
_VALID_WEIGHTS = {"bull_wins", "bear_wins", "balanced"}
_VALID_CONFIDENCE = {"high", "medium", "low"}


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # Drop opening fence (```json or ```)
        if "\n" in text:
            text = text.split("\n", 1)[1]
        # Drop closing fence
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


def _build_additional_rounds_block(
    bull_rounds: list[str], bear_rounds: list[str]
) -> str:
    """Format rounds 2..N (1-indexed: rounds[1:]) as alternating
    'Bear rebuttal i' / 'Bull rebuttal i' blocks."""
    parts: list[str] = []
    extra = max(len(bull_rounds), len(bear_rounds)) - 1
    for i in range(1, extra + 1):
        if i < len(bear_rounds):
            parts.append(f"\nBear rebuttal {i}:\n\"\"\"\n{bear_rounds[i]}\n\"\"\"")
        if i < len(bull_rounds):
            parts.append(f"\nBull rebuttal {i}:\n\"\"\"\n{bull_rounds[i]}\n\"\"\"")
    return "\n".join(parts)


def parse_facilitator_response(text: str) -> dict[str, Any]:
    """Parse the facilitator's response into a structured dict.

    Tolerates: leading markdown fences, missing reasoning paragraph,
    JSON formatting quirks. Returns a dict with `verdict`,
    `suggested_action`, `confidence`, etc., with defaults if any field
    is absent or the JSON itself is malformed."""
    cleaned = _strip_markdown_fence(text)
    json_line, _, rest = cleaned.partition("\n")
    json_line = _strip_markdown_fence(json_line).strip()
    parsed: dict[str, Any]
    try:
        parsed = json.loads(json_line)
    except json.JSONDecodeError:
        # Malformed JSON: fall back to defaults but keep the raw text.
        return {
            "verdict": "thesis_neutral",
            "weight": "balanced",
            "key_evidence_for_verdict": "",
            "key_trigger_to_monitor": "",
            "suggested_action": "maintain",
            "confidence": "low",
            "reasoning": cleaned,
            "_parse_error": "json_decode_failed",
        }
    out: dict[str, Any] = {
        "verdict": (
            parsed.get("verdict")
            if parsed.get("verdict") in _VALID_VERDICTS
            else "thesis_neutral"
        ),
        "weight": (
            parsed.get("weight")
            if parsed.get("weight") in _VALID_WEIGHTS
            else "balanced"
        ),
        "key_evidence_for_verdict": parsed.get("key_evidence_for_verdict", ""),
        "key_trigger_to_monitor": parsed.get("key_trigger_to_monitor", ""),
        "suggested_action": parsed.get("suggested_action", "maintain"),
        "confidence": (
            parsed.get("confidence")
            if parsed.get("confidence") in _VALID_CONFIDENCE
            else "low"
        ),
        "reasoning": rest.strip(),
    }
    return out


def facilitate_debate(
    ticker_data: dict[str, Any],
    bull_rounds: list[str],
    bear_rounds: list[str],
) -> dict[str, Any] | None:
    client = get_client()
    if client is None:
        return None
    if not bull_rounds or not bear_rounds:
        return None
    additional = _build_additional_rounds_block(bull_rounds, bear_rounds)
    prompt = FACILITATOR_PROMPT_TMPL.format(
        ticker=ticker_data.get("ticker", "?"),
        bull_initial=bull_rounds[0],
        bear_initial=bear_rounds[0],
        additional_rounds=additional,
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=FACILITATOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        text = getattr(block, "text", None)
        if not text:
            return None
        return parse_facilitator_response(text)
    except Exception as exc:  # noqa: BLE001
        print(f"Facilitator error for {ticker_data.get('ticker')}: {exc}")
        return None

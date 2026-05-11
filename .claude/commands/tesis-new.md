---
name: tesis-new
description: Generate a fresh fundamental thesis on a single ticker, gated by universe pre-filter and adversarially reviewed by red-team before publication. Output is a Spanish-readable thesis with calibrated confidence, invalidation criteria, and red-team challenges.
argument-hint: "<TICKER>"
---

# /tesis-new — New fundamental thesis on a ticker

You are the Coordinator. The user has asked for a fundamental investment thesis on a single security. Run the full thesis pipeline: universe pre-filter → fundamental analysis → adversarial review → persistence → Spanish surfacing.

## Purpose

Produce a decision-grade fundamental thesis the user can rely on for `real` portfolio decisions, complying with CLAUDE.md §11 Financial Chain-of-Thought and §6 universe restriction.

## Preconditions

1. `$1` is non-empty and looks like a plausible ticker (alphanumeric, ≤ 6 chars typical; allow exchange suffix e.g. `ASML.AS`). If empty, abort: *"Indica un ticker: /tesis-new ASML"*.
2. System is initialized (`SYSTEM_T0` set).
3. The user has NOT explicitly rejected this ticker within the last 6 months. Check `data/events/decisions.jsonl` for prior `user_decision: "reject"` on this ticker. If found, ask the user: *"Rechazaste TICKER el YYYY-MM-DD. ¿Quieres analizarlo de nuevo? (sí/no)"*. Abort if answer is "no".

## Execution sequence

### Step 1 — Resolve ticker

Resolve `$1` to a canonical `(ticker, isin, exchange)` triple via yfinance/OpenBB. If resolution fails or is ambiguous, ask the user to disambiguate before continuing. Persist the resolution in the thesis bundle for audit.

### Step 2 — Universe pre-filter (delegate to fundamental-analyst)

Invoke `fundamental-analyst` agent with the resolved ticker. The agent runs §1 universe pre-filter as its first step (accessibility / liquidity / data coverage / fiscal sanity / Lightyear availability / size sanity).

**If pre-filter fails**: the agent appends a `rejection` event to `data/events/theses/{ticker}.jsonl` with the failing reason code. Surface to user in Spanish: *"TICKER rechazado: [razón concreta]. No procede análisis profundo."* End command.

### Step 3 — Full fundamental analysis (delegated)

If pre-filter passes, the same `fundamental-analyst` invocation continues with the three-layer FinCoT (Data → Concept → Thesis) and the valuation triad (DCF + reverse DCF + peer multiples). It appends a `thesis` event to `data/events/theses/{ticker}.jsonl`.

Read the resulting event. Capture `confidence_calibrated`, `recommendation`, `dispersion_pct`, key risks.

### Step 4 — Adversarial review (red-team)

If `confidence_calibrated > 0.70` AND `recommendation ∈ {buy, add}`, invoke `red-team` against the just-published thesis event. Pass the thesis's `event_id` and the content-addressed bundle hash.

The `red-team` will run all five attacks (sycophancy, cherry-picking, look-ahead, base-rate, survivorship) and append a `red_team_review` event to `data/events/red_team_reviews.jsonl`.

**Interpret the verdict** per `red-team` §3:
- `overall_verdict: "block"` → DO NOT surface thesis to user. Return to `fundamental-analyst` with the blocking challenges; the user sees only that the thesis is under revision.
- `overall_verdict: "conditional_pass"` → surface thesis AND material challenges side by side.
- `overall_verdict: "pass"` → surface thesis with a one-line "red-team pasó sin objeciones materiales".

Below the `confidence_calibrated > 0.70` threshold, skip red-team (per `red-team` §1 invocation rules).

### Step 5 — Optional quantitative bound (quant-modeler)

If the thesis includes a reverse-DCF implied price target, optionally invoke `quant-modeler` in single-ticker mode at horizons {1y, 3y, 5y} to compute `implied_probability_above_target`. This is an enrichment, not a blocker — proceed without it if calibration data is insufficient.

Persist the quant simulation event if it runs.

### Step 6 — Persist coordinator decision

Append a `decision` event to `data/events/decisions.jsonl`:

```json
{
  "event_type": "coordinator_decision",
  "ts": "...",
  "command": "tesis-new",
  "ticker": "ASML",
  "thesis_event_id": "thesis-asml-...",
  "red_team_verdict": "conditional_pass",
  "quant_modeler_event_id": "sim-asml-...",
  "user_action_required": "review_and_decide",
  "inputs_hash": "sha256:..."
}
```

And a `run` event to `data/events/runs.jsonl`.

## Output to user (Spanish)

Lead with the conclusion. Format:

```
📊 Tesis nueva: <TICKER>

Conclusión: <BUY | HOLD | WATCH | PASS> | Confianza: 0.XX

Por qué (3-4 frases):
<layer_3_thesis traducido al español>

Valoración:
- DCF FCFF: XXX <currency> por acción
- Reverse DCF implícito g = X.X% (interpretación: alta/razonable/exigente)
- Múltiplos comparables: rango YYY-ZZZ
- Precio actual: WWW. Dispersión entre métodos: AA%.

Qué debe ser cierto (must_be_true):
1. ...
2. ...
3. ...

Qué invalidaría la tesis (would_falsify):
1. ...
2. ...
3. ...

Red-team [PASS | CONDITIONAL PASS | BLOCK]:
<si conditional_pass: lista de challenges materiales con required_response>

Pr(precio > target a 3 años) según quant-modeler: NN%
Rango P25-P75 a 3 años: AAA-BBB <currency>

⚠️ Riesgos clave:
- ...
- ...
```

If the recommendation is `buy` or `add`, end with: *"Si decides ejecutar, hazlo manualmente en Lightyear y luego corre /ingest-lightyear-csv para reflejarlo en `real`."*

If `red-team` blocked the thesis, output a brief: *"La tesis fue bloqueada por red-team. Está en revisión. Re-ejecuta /tesis-new TICKER cuando quieras re-intentar con el feedback aplicado."*

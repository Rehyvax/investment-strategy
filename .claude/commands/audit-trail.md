---
name: audit-trail
description: Reconstruct the full context of a past decision. Given a decision ID, loads the content-addressed input bundle, replays which agents participated, what data they saw at point-in-time, and what each one concluded. Output is a Spanish-readable timeline with verbatim citations. Strictly read-only.
argument-hint: "<DECISION_ID>"
---

# /audit-trail — Reconstruct a past decision

You are the Coordinator. The user wants to understand exactly what happened around a specific decision in the past — which agents ran, what they saw, what they said. Strictly read-only; produces no new state.

## Purpose

Make the audit trail accessible. The system's correctness depends on point-in-time discipline; this command lets the user verify it by examining any historical decision.

## Preconditions

1. `$1` is non-empty and corresponds to an existing decision. Decision IDs follow the convention `<command>-<ticker_or_scope>-<YYYY-MM-DD>-<NNN>` (e.g., `tesis-new-ASML-2026-04-15-001`) or any other unique identifier persisted in `data/events/decisions.jsonl`.
2. If the ID doesn't resolve, surface candidates: list the 10 most recent decision IDs and ask the user to pick one.
3. **NEVER** write any state. This command does not append to JSONL, does not modify caches, does not refresh snapshots.

## Execution sequence

### Step 1 — Locate the decision event

Search `data/events/decisions.jsonl` for the event with matching ID. Use grep on the JSON `id` or composite key. If multiple matches (shouldn't happen but defend against it), pick the earliest and warn.

If not found, list the 10 most recent decisions sorted by `ts` desc, in Spanish, and end. Suggested format:

```
No encuentro decisión "<$1>". Decisiones recientes:
- tesis-new-ASML-2026-05-10-001   (2026-05-10 14:32)
- rebalance-propose-real-2026-05-08-001   (2026-05-08 11:15)
- ...
Vuelve a llamar con un ID válido.
```

### Step 2 — Load the input bundle

Each persisted decision references `inputs_hash`. The content-addressed bundle lives at `data/audit/{first_two_chars_of_hash}/{full_hash}.json.zst`.

Decompress and parse. The bundle contains:
- The exact prompts passed to each agent
- The exact responses received
- A manifest of file reads (path + sha256 of content at the time of read)
- Timestamps for every step

If the bundle is missing or corrupted, mark `bundle_unavailable` and proceed with the partial reconstruction from `decisions.jsonl` + the agent's event log only (degraded mode). Surface the degradation explicitly to the user.

### Step 3 — Identify participating agents

From the decision event's references (`thesis_event_id`, `risk_assessment_event_id`, `tax_assessment_event_id`, `red_team_review_event_id`, `quant_modeler_event_id`, `regime_assessment_id`, etc.), enumerate the agents that contributed.

For each agent, locate its specific event in the corresponding JSONL stream and extract:
- The agent's `reasoning` field
- The agent's `confidence_calibrated` and `confidence_justification`
- The agent's verdict (if applicable: approve/warn/veto/block/conditional_pass/pass)
- The agent's `point_in_time_date` used

### Step 4 — Build the timeline

Order events by `ts` ascending. Annotate each entry with:
- Agent name
- Inputs (compressed list of file paths + data sources)
- Output summary (lifted from `reasoning` field, max 3 sentences)
- Verdict (where applicable)
- Confidence

### Step 5 — Verify point-in-time integrity

For each data source cited by each agent, verify the source's date is ≤ the decision's `point_in_time_date`. If ANY source predates `point_in_time_date` improperly (i.e., a future-dated file slipped in), flag as `look_ahead_violation_detected` — this is a serious audit finding and should be surfaced loudly.

Also verify the prompts in the bundle don't reference data later than the bundle's claimed `point_in_time_date`.

## Output to user (Spanish, factual, no editorializing — per CLAUDE.md §13)

Lead with the final coordinator decision verdict surfaced at the top of the
reconstruction (one-line bottom line), then the chronological timeline below
as supporting evidence. For an audit-trail, the "conclusion" is the decision
that was ultimately taken; the timeline is the reasoning trail.

```
🔍 Reconstrucción de decisión: $1

Tipo: <thesis | rebalance | macro_call | risk_assessment | ...>
Fecha: YYYY-MM-DD HH:MM:SS UTC
Punto-en-tiempo (point_in_time_date): YYYY-MM-DD
Inputs hash: sha256:abc... (bundle <disponible | NO disponible>)

Timeline:

[10:15:00] fundamental-analyst (modelo: opus-4-7)
  Inputs: data/events/prices/2026-04.jsonl (sha256:xyz...), SEC 20-F (2026-02-15)
  Conclusión: BUY ASML, conf 0.72.
  Cita literal del Layer 3 thesis:
    "ASML retains EUV monopoly through 2030+ given 8-year tech lead..."
  Tres conditions must_be_true: [...]
  Tres would_falsify: [...]

[10:32:00] risk-concentration (modelo: opus-4-7)
  Inputs: snapshot real (2026-04-29), data/events/prices/...
  Verdict: APPROVE post-trade. Concentración tech post-trade: 38% (≤40% para aggressive).
  Cita: "Single-name max ASML 9.4%, top-5 41%. Sin breaches."

[10:48:00] red-team (modelo: opus-4-7)
  Inputs: thesis-asml-2026-04-29-001 bundle
  Verdict: CONDITIONAL PASS. 2 challenges materiales:
    - cherry_picking: peer set omitió Canon, Nikon. Required response: ...
    - base_rate: conf 0.72 está +0.12 sobre base rate histórico. Required response: ...
  Sin challenges blocking.

[11:00:00] coordinator decision: tesis-new-ASML-2026-04-29-001
  Surface al usuario: thesis + 2 challenges materiales.
  user_action_required: review_and_decide.

✅ Verificación point-in-time: OK. Todas las fuentes citadas tienen fecha ≤ 2026-04-29.
```

If a `look_ahead_violation_detected` is found, prepend a red banner: *"⚠️ ATENCIÓN: Detectada posible violación point-in-time en esta decisión. Detalle: [archivo X tiene fecha YYYY-MM-DD posterior a point_in_time_date]. Esto requiere investigación — el audit trail puede estar comprometido."*

If `bundle_unavailable`, end with: *"Reconstrucción degradada (bundle no encontrado). Datos basados solo en JSONL events. Para reconstrucción completa, restaurar data/audit/ desde backup."*

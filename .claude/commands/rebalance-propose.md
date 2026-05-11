---
name: rebalance-propose
description: Propose a rebalance for a specific portfolio. For competitive portfolios (aggressive/conservative/value/momentum/quality), applies the immutable charter mechanically. For real or shadow, orchestrates fundamental-analyst, risk-concentration, macro-regime, rebalancing-tax, and red-team for a fully reviewed proposal. Output is trade-by-trade with tax impact and red-team challenges; the user executes manually in Lightyear.
argument-hint: "<PORTFOLIO_ID> (real | shadow | aggressive | conservative | value | momentum | quality | benchmark_passive)"
---

# /rebalance-propose — Propose a rebalance

You are the Coordinator. The user wants a trade proposal for a specific portfolio. This command never executes — it produces a structured proposal the user reviews and (for `real`) executes manually in Lightyear.

## Purpose

Generate a rebalance proposal that respects the portfolio's charter, current risk limits, regime modulators, Spanish tax rules, and adversarial review. The proposal is decision-grade: the user can act on it directly or veto it.

## Preconditions

1. `$1` is non-empty and ∈ `{real, shadow, aggressive, conservative, value, momentum, quality, benchmark_passive}`. Otherwise abort: *"Indica una cartera válida. Opciones: real, shadow, aggressive, conservative, value, momentum, quality, benchmark_passive."*
2. `data/snapshots/$1/latest.json` exists and is current (within the last trading day).
3. System has run `/daily-cycle` at least once today (prices and snapshots fresh).

## Execution sequence

### Step 1 — Load portfolio context

Read:
- `data/snapshots/$1/latest.json` for current holdings, weights, cash.
- The charter for `$1`. For competitive portfolios, the charter is encoded in CLAUDE.md §10. For `real` and `shadow`, there is no immutable charter — the proposal is open-ended within the universe and risk limits.
- Recent regime assessment: `tail -1 data/events/regime_assessments.jsonl`.

### Step 2 — Branch by portfolio kind

#### Branch A — `benchmark_passive`

This portfolio's allocation is immutable (70/20/10 IWDA/VFEM/IEAG). The only rebalancing is to restore target weights if they drift > 3pp on any leg.

- Compute current weights, identify drift.
- If max drift ≤ 3pp: surface to user *"benchmark_passive dentro de tolerancia. Sin rebalanceo necesario."* End.
- Otherwise: construct the minimal trade set that restores 70/20/10. Skip Steps 3-6 (no fundamental/risk/regime/tax reasoning needed; allocation is fixed). Output proposal directly.

#### Branch B — Competitive portfolios (`aggressive`, `conservative`, `value`, `momentum`, `quality`)

The charter (CLAUDE.md §10) defines the rebalance rule mechanically:
- `aggressive`: mean-variance max-Sharpe + momentum tilt, max 12 holdings, 100% equity allowed, quarterly.
- `conservative`: Risk Parity, ≤ 8% per asset, ≥ 20% MMF/short bonds, monthly.
- `value`: equal-weight top-15 by fundamental value score + Piotroski ≥ 7, annual full / quarterly review.
- `momentum`: top decile of 12m-1m total return, equal weight, top 20, quarterly.
- `quality`: ROIC > WACC sustained 5y + HRP weighting, 15-20 holdings, semi-annual.

Apply the rule using:
- `src/portfolios/{charter}_engine.py` for the candidate universe and target weights.
- `fundamental-analyst` only for quality/value gating (Piotroski, ROIC vs WACC); the engine handles selection mechanically.
- `risk-concentration` for charter-specific concentration limits + HRP weights (`quality`).
- `rebalancing-tax` to compute trade-by-trade tax impact even though paper portfolios have `fiscal_relevance: simulated_only`.

Skip macro-regime modulators for `momentum` and `aggressive` (their charters are timing-aware by design). Apply them for `quality`, `conservative`, `value`.

#### Branch C — `real` or `shadow` (full pipeline)

This is the high-stakes path. Run the full agent orchestration:

1. **Macro modulators**: read latest `regime_assessment` → extract `risk_appetite_multiplier`, `quality_floor_uplift`, `min_cash_pct_override`, `new_position_max_size_pct_multiplier`, `conviction_required`. These bias the entire proposal.

2. **Candidate generation**: identify candidate names. For ADD/HOLD, use existing positions. For BUY, consult the user inline: *"¿Tienes candidatos concretos para añadir, o quieres que te proponga desde tesis vivas de alta convicción?"*. If the user defers, list theses in `data/events/theses/` filtered to `recommendation: buy` AND `confidence_calibrated ≥ conviction_required` AND age < 90 days.

3. **Per-candidate validation**: for each BUY candidate, ensure a current thesis exists. If not, ask the user to run `/tesis-new TICKER` first. Do not BUY without a thesis (CLAUDE.md §14).

4. **Weight optimization**: invoke `risk-concentration` to propose weights via HRP (with charter-specific cap overrides), passing the validated candidate list. The agent applies the regime's `risk_appetite_multiplier` to its budget.

5. **Trade construction**: take the target weights, compute the trades needed to move from current snapshot to target, ordered to minimize commission cost (use `src/portfolios/cost_model.py::lightyear_cost`).

6. **Tax review**: invoke `rebalancing-tax` (quiet mode for `real`, simulated mode for `shadow`) to validate each trade — FIFO consumption, 2-month rule check, hard vetoes per its §4. If any veto fires, modify the trade per `minimal_remediation` suggestions and re-validate.

7. **Risk veto check**: re-invoke `risk-concentration` with the post-trade portfolio to verify no §2 concentration limit is breached. If breached and not already addressed, modify trades (smallest possible) until clean.

8. **Adversarial review**: invoke `red-team` against the integrated proposal (turnover > 10% NAV triggers it per `red-team` §1). Pass the proposal as the bundle.

### Step 3 — Persist proposal

Append a `rebalance_proposal` event to `data/events/decisions.jsonl`:

```json
{
  "event_type": "rebalance_proposal",
  "ts": "...",
  "command": "rebalance-propose",
  "portfolio_id": "$1",
  "branch": "benchmark | competitive | full",
  "trades": [
    {"side": "buy", "ticker": "...", "quantity": 5, "estimated_price_eur": ..., "estimated_value_eur": ..., "thesis_event_id": "...", "fifo_impact": "..."},
    ...
  ],
  "estimated_total_commission_eur": ...,
  "estimated_tax_impact_eur": ...,
  "risk_assessment_event_id": "...",
  "tax_assessment_event_id": "...",
  "red_team_review_event_id": "...",
  "regime_context": {"label": "Bull", "modulators": {...}},
  "user_action_required": "manual_execution_in_lightyear | none",
  "inputs_hash": "sha256:..."
}
```

For paper portfolios, the trades are auto-applied (the portfolio engine executes the proposal immediately; no manual user step). For `real`, the trades are listed but require manual user execution.

Append a run event to `data/events/runs.jsonl`.

## Output to user (Spanish)

Lead with the bottom line. Format:

```
🔄 Propuesta de rebalanceo: $1

Régimen actual: <label> | Riesgo nominal: <multiplier>x | Cash mínimo regimen-override: X%

Trades propuestos (N):
1. COMPRAR  10 ASML @ ~720 € = 7.200 € | Tesis 2026-04-15, conf 0.74 | Comisión: 1 €
2. VENDER    5 INTC @ ~24 USD = 110 € | FIFO: lote del 2024-Q3, plusvalía 12 € | Impacto fiscal: ~2,3 €
3. ...

Comisión total estimada: X €
Impacto fiscal estimado (sólo `real`): Y € (regla 2 meses: sin afectación | aviso: ...)
Turnover proyectado: Z% NAV

Red-team verdict: <pass | conditional_pass | block>
<si conditional_pass: lista de material challenges>
<si block: no surfacing; ver más abajo>

⚠️ Alertas concentración: <si las hay>
```

For paper portfolios, end with: *"Trades aplicados automáticamente a `$1` (paper portfolio). Ver impacto en próximo /daily-cycle."*

For `real`, end with: *"Ejecuta manualmente en Lightyear. Después, /ingest-lightyear-csv para reflejarlo. Si decides NO ejecutar, el portfolio `shadow` registrará la divergencia."*

If red-team blocked, output: *"Propuesta bloqueada por red-team. Razones: [breve resumen]. La propuesta NO se persistió como ejecutable. Re-ejecuta /rebalance-propose $1 cuando los challenges se hayan resuelto."*

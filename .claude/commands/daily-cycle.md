---
name: daily-cycle
description: Run the daily operational cycle. News scan, EOD price refresh, snapshot recompute for all 8 portfolios, then conditional invocations of macro-regime (weekly Monday), performance-evaluator (monthly 1st / quarterly first Monday / annual Jan 15), and quant-modeler (quarterly first Monday). Surfaces CRITICAL/HIGH alerts inline and pauses for user attention.
---

# /daily-cycle — Operational cadence orchestrator

You are the Coordinator. Run the full operational cadence for *today*, conditional on the calendar. This command is safe to run every weekday morning; it self-detects which cadence layers apply (weekly Monday, monthly 1st, quarterly first Monday, annual Jan 15).

## Purpose

Single command that synchronizes the lab with the current trading day. Compliant with CLAUDE.md §12 operating cadences after the alignment to weekly macro-regime cadence.

## Preconditions

1. `/onboarding` has been run (`SYSTEM_T0` set in `.env`).
2. All 8 portfolios have a snapshot in `data/snapshots/*/latest.json`.
3. Today is a trading day (Mon–Fri, not an exchange holiday); if not, run a *partial* cycle (news + price refresh only) and inform the user.

## Execution sequence

### Step 1 — Determine cadence flags for today

Compute booleans:
- `is_trading_day` (Mon–Fri, not in exchange-holiday calendar)
- `is_monday` (true Monday)
- `is_first_business_day_of_month` (1st of month, or Monday after weekend)
- `is_first_monday_of_quarter` (first Monday of Jan/Apr/Jul/Oct)
- `is_jan_15_or_first_business_day_after` (annual review trigger; coincides with Modelo 720)

Persist these flags into a `daily_cycle_start` event in `data/events/runs.jsonl`.

### Step 2 — News scan (always)

Invoke the `news-scanner` agent over the union of tickers currently held in any active portfolio (from `data/snapshots/*/latest.json`).

After completion, read the newly appended events in `data/events/news_events.jsonl` and filter by `severity ∈ {critical, high}`.

**If any CRITICAL or HIGH event exists**:
- Surface a Spanish alert to the user IMMEDIATELY, formatted per CLAUDE.md §13 (lead with conclusion).
- PAUSE the cycle. Ask the user: *"¿Continúo con el resto del ciclo diario o paro aquí para que revises?"*
- Continue only after explicit user confirmation.

Otherwise, log a one-line summary and continue silently.

### Step 3 — EOD price refresh

For every ticker held in any portfolio + the benchmark constituents (IWDA, VFEM, IEAG), pull EOD prices via `yfinance` for the most recent close that is `< now`. Append to `data/events/prices/YYYY-MM.jsonl` (auto-rotate by month).

Skip tickers that already have today's close persisted (idempotent).

### Step 3.5 — Flight-to-safety market indicators pull

Run `scripts/flight_to_safety_pull.py` to persist today's snapshot of five descriptive macro/risk indicators (GLD, DXY, UST10Y, VIX term structure, TLT/SPY bond-equity ratio) into `data/market_indicators/flight_to_safety/{system_date}.json`.

**Failure handling**: if yfinance fails for any individual indicator, the script marks that indicator `stale: true` and continues with the others. Failure of this step does NOT block the rest of `/daily-cycle` — at most logs a one-line warning. The dashboard layer treats stale indicators visibly.

**Interpretation**: this layer is **descriptive only, never prescriptive**. The Coordinator does NOT translate indicator levels into BUY/SELL recommendations; the indicators are persisted for the user to consult alongside the portfolios. Canonical interpretation notes (e.g., "DXY > 100 historically associates with USD strength / risk-off") are persisted inline in each indicator block as labels, not actions.

### Step 3.6 — Sector flows GICS pull (dashboard Layer 1)

Run `scripts/sector_flows_pull.py` to persist today's snapshot of the 11 Select Sector SPDR ETFs (XLE, XLB, XLI, XLY, XLP, XLV, XLF, XLK, XLC, XLU, XLRE) into `data/market_indicators/sector_flows/{system_date}.json`.

**Per-sector metrics**: close USD, YTD / 1M / 3M / 6M / 1Y returns, `above_ma200` flag + distance from MA200, 30-day annualized realized volatility, approximate static S&P 500 weight, best-effort forward P/E via yfinance `.info`.

**Failure handling**: per-ticker errors mark that sector `stale: true` and continue. Failure of this step does NOT block `/daily-cycle`.

**Interpretation**: descriptive only, never prescriptive. The Coordinator does NOT translate sector ranks or breadth metrics into "rotate into X / out of Y" recommendations. The S&P 500 weights are approximate static references (re-validated periodically against the canonical S&P index methodology document), not real-time index weights.

### Step 4 — Snapshot recompute for the 8 portfolios

Invoke `src/portfolios/snapshot.py --all --date today`. Persist `data/snapshots/{portfolio_id}/{YYYY-MM-DD}.json` for each portfolio, then update the symlink/copy `latest.json` for each.

### Step 5 — Weekly cadence (Monday only)

If `is_monday`:
- Invoke `macro-regime` agent for its weekly HMM forward-pass update. The agent enforces the once-per-week rule internally.
- If `derived_label` changed vs. last week, surface the change to the user.

### Step 6 — Monthly cadence (1st business day of month)

If `is_first_business_day_of_month`:
- Invoke `performance-evaluator` with `report_type: monthly_light`.
- Read the resulting Spanish summary and surface to user.
- If the report flags a portfolio with material drift (factor exposure inconsistent with charter, sustained underperformance), include the warning prominently.

### Step 7 — Quarterly cadence (first Monday of Jan/Apr/Jul/Oct)

If `is_first_monday_of_quarter`:
- Invoke `quant-modeler` in `quarterly_batch` mode (full scenario sets for the 8 portfolios + 4 historical stress tests).
- Invoke `performance-evaluator` with `report_type: quarterly_full` (consumes the quant-modeler output for stress-test rows).
- Surface the quarterly summary to the user; this is the deepest user-facing report.

### Step 8 — Annual cadence (January 15 or next business day)

If `is_jan_15_or_first_business_day_after`:
- Invoke `performance-evaluator` with `report_type: annual`.
- Invoke `rebalancing-tax` in `compliance` mode → effectively delegates to `/modelo-720-check` flow.
- Bundle outputs into a single annual review surfaced to user.

### Step 9 — Persist cycle completion

Append `daily_cycle_complete` event to `data/events/runs.jsonl` with:
- Which cadence layers ran (booleans from Step 1)
- Wall-clock duration
- Counts of news events, price points refreshed, snapshots produced
- Pointer to any alerts surfaced

## Output to user (Spanish)

Always end with a compact cycle summary. Example for a typical Tuesday with no alerts:

```
✅ Ciclo diario completado (2026-05-12, martes).

📰 Noticias: 12 eventos persistidos, 0 CRITICAL/HIGH.
💹 Precios EOD: 47 tickers actualizados.
📸 Snapshots: 8/8 carteras a 2026-05-12.

Sin cadencias semanales/mensuales/trimestrales activas hoy.
Próxima cadencia: lunes 2026-05-18 → macro-regime weekly update.
```

Example for a Monday with regime change:

```
✅ Ciclo completado (2026-05-11, lunes).

📰 Noticias: 18 eventos, 0 CRITICAL, 1 HIGH (MSFT downgrade JPM).
💹 Precios EOD: 47 tickers.
📸 Snapshots: 8/8 carteras.
🌐 Régimen: CAMBIO Bull → Sideways. P(sideways) = 0.62 (≥0.50 cumple criterio). Modulators activados: quality_floor +0, min_cash_pct override 5%.
```

When a CRITICAL alert paused the cycle, the output is the alert itself plus *"Ciclo en pausa. Confirma con 'continuar' para reanudar"*.

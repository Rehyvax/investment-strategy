---
name: ingest-lightyear-csv
description: Synchronize the real portfolio against a Lightyear CSV export. Parses trades/dividends/FX, deduplicates against existing trade log, updates the FIFO lot ledger via rebalancing-tax, and reconciles NAV. Aborts if reconciled NAV diverges from CSV by > 0.5%.
argument-hint: "[csv_filename] (optional; defaults to newest .csv in data/inbox/lightyear/)"
---

# /ingest-lightyear-csv — Lightyear CSV reconciliation

You are the Coordinator. The user has dropped (or will drop) a Lightyear export CSV in `data/inbox/lightyear/`. Your job is to import new operations idempotently into the `real` portfolio's audit trail.

## Purpose

Keep the `real` portfolio's `trades.jsonl` and FIFO lot ledger in lockstep with the user's actual broker state, with a hard reconciliation guard against silent drift.

## Preconditions

1. `data/events/portfolios/real/trades.jsonl` MUST exist (otherwise run `/onboarding` first).
2. A CSV file exists in `data/inbox/lightyear/`. If `$1` is provided, use that specific file; otherwise use the most recently modified `.csv`.
3. `data/cache/fx_rates.duckdb` is populated for the date range covered by the CSV (or can be backfilled from ECB).

## Execution sequence

### Step 1 — Locate and parse CSV

Resolve the target file:
- If `$1` is non-empty, use `data/inbox/lightyear/$1`.
- Otherwise, list `*.csv` in `data/inbox/lightyear/` sorted by mtime descending; take the first.
- If no CSV is found, abort with Spanish: *"No encuentro ningún CSV en data/inbox/lightyear/. Exporta el extracto desde Lightyear y vuelve a intentarlo."*

Invoke `src/ingestion/lightyear_csv.py --file <path>` to parse the CSV into a normalized stream of `trade` / `dividend` / `fx_conversion` / `interest` / `corporate_action` events. The parser owns the schema mapping; you do not parse columns yourself.

### Step 2 — Deduplicate against existing log

For each parsed event:
- Compute a canonical hash: `sha256(trade_date || ticker || side || quantity || unit_cost_native)`.
- Read `data/events/portfolios/real/trades.jsonl` and skip any event whose hash already exists.
- Persist the surviving events as candidate appends.

Report to the user, before committing: *"He encontrado N nuevas operaciones; M duplicadas omitidas."*

### Step 3 — FIFO lot ledger update (delegate to rebalancing-tax)

Invoke `rebalancing-tax` agent in quiet-mode validation pass for each new event. The agent will:
- For BUY events: register a new lot in `data/state/lots/real/{isin}.jsonl`.
- For SELL events: consume lots in FIFO order, append `lot_consumption` events to `data/events/portfolios/real/lot_consumptions.jsonl`, compute realized P&L in EUR.
- For SELL-at-LOSS events: trigger the 2-month rule check; if the rule applies, flag and surface to user before commit (DO NOT auto-skip — the user may have informed reasons).
- For corporate actions (splits, spinoffs): apply lot-adjustment events deterministically.

### Step 4 — Reconcile NAV

After all events are conceptually applied (still in-memory, not yet committed), recompute the `real` portfolio's NAV in EUR using:
- Holdings × current prices (yfinance EOD for `trade_date_last`)
- Cash balance derived from the trade log + interest + dividends - commissions - FX costs

Compare against `nav_reported_eur` extracted from the CSV (the parser surfaces this when Lightyear's export includes a NAV line; otherwise skip this step with a `nav_reconciliation_skipped` warning).

**Hard guard**: if `|nav_computed - nav_reported| / nav_reported > 0.005` (0.5%), ABORT the commit. Report to user in Spanish: *"Discrepancia de reconciliación: NAV calculado X €, NAV reportado por Lightyear Y €, diferencia Z€ (Z.Z%). No realizo el commit. Posibles causas: FX rate mismatch, corporate action no detectada, columna no parseada. Inspecciona el CSV."*

### Step 5 — Commit

If reconciliation passes:
- Append all new events to `data/events/portfolios/real/trades.jsonl` atomically (write to temp, fsync, rename).
- Append `lot_consumption` events to `data/events/portfolios/real/lot_consumptions.jsonl`.
- Update `data/state/lots/real/{isin}.jsonl` files.
- Append a `csv_ingest_complete` event to `data/events/decisions.jsonl` with the source filename, event count, and reconciled NAV.
- Append a run event to `data/events/runs.jsonl`.
- Move the consumed CSV to `data/inbox/lightyear/processed/{YYYY-MM-DD}_{original_name}` to prevent double-ingest.

### Step 6 — Refresh snapshot

Trigger `src/portfolios/snapshot.py --portfolio real` to update `data/snapshots/real/latest.json`.

## Output to user (Spanish)

```
✅ Ingesta completada.

Archivo: <csv_filename>
Operaciones nuevas: N (compras: A, ventas: B, dividendos: C, FX: D)
Operaciones duplicadas omitidas: M
NAV calculado: XX.XXX,XX €
NAV reportado por Lightyear: YY.YYY,YY €
Diferencia: Z,Z€ (Z,Z%)  ← dentro de tolerancia 0,5%

Lots ledger actualizado: K ISINs afectados.
2-meses regla: J avisos (revisar abajo) | sin avisos
```

If 2-month rule warnings are present, list them as bullets with the specific ISIN, sell date, recent buy date, and deferred-loss amount. Always end with: *"Próximo paso sugerido: /daily-cycle si no se ha ejecutado hoy."*

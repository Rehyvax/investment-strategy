---
name: onboarding
description: Bootstrap the lab on first run. Captures the user's current Lightyear holdings, creates the 6 paper portfolios with 50,000 € cash each, builds the benchmark_passive portfolio at T0, and fixes SYSTEM_T0 in .env. Strictly idempotent — refuses to run twice.
---

# /onboarding — System bootstrap

You are the Coordinator. The user is running this command for the first time. Your job is to take the lab from empty filesystem to a fully initialized 8-portfolio state, with `T0 = today` written immutably into the audit trail.

## Purpose

Take the lab from zero to a clean initialized state with all 8 portfolios live at T0 = today, ready to receive the daily/weekly/monthly cadences defined in CLAUDE.md §12.

## Preconditions (verify BEFORE doing anything)

1. `data/events/portfolios/real/trades.jsonl` must NOT exist. If it exists, abort with a clear Spanish message: *"El sistema ya está inicializado. Esta operación no es repetible. Si quieres re-bootstrapping, borra manualmente data/events/portfolios/ y los snapshots."*
2. `.env` file exists (or can be created). If `SYSTEM_T0` is already set, abort with the same message.
3. The user is in front of the keyboard — this is an interactive command. Do not run unattended.

## Execution sequence

### Step 1 — Capture real holdings (interactive)

Ask the user, in Spanish, to paste their current Lightyear positions in free format (one position per line, with ticker/ISIN/quantity/avg-cost-or-current-value). Accept any reasonable format; do not impose a schema upfront. Examples to suggest:

```
MSFT 10 acciones, comprado a 380 USD avg
ASML 3 acciones, valor actual 2100 EUR cada una
IWDA (IE00B4L5Y983) 25 participaciones, comprado a 85.40 EUR
Cash EUR 12000
```

If the user has no positions yet (a fresh investor starting from cash), accept `cash: 50000 EUR` as the only entry and skip equity normalization.

### Step 2 — Normalize positions

For each declared position:
- Resolve the ISIN if only the ticker is given (use yfinance metadata first; fall back to asking the user).
- Identify the exchange and currency.
- Verify the position complies with CLAUDE.md §6 universe restriction. If a forbidden asset is declared (e.g., a US-domiciled ETF, a leveraged ETF), warn the user explicitly that the system cannot manage it but will record it in `real` for accounting purposes. Tag with `universe_compliant: false`.
- For positions where the user provides only a current value (no avg cost), accept it as the initial cost-basis at T0. Document this assumption in the trade event.

### Step 3 — Write `real` portfolio trades

Create `data/events/portfolios/real/trades.jsonl` with one event per holding:

```json
{
  "event_type": "trade",
  "trade_kind": "initial_position",
  "ts": "<T0 ISO timestamp>",
  "trade_date": "<T0 YYYY-MM-DD>",
  "ticker": "MSFT",
  "isin": "US5949181045",
  "exchange": "NASDAQ",
  "currency": "USD",
  "quantity": 10.0,
  "unit_cost_native": 380.0,
  "unit_cost_eur": <FX-converted>,
  "fx_rate": <ECB rate at T0>,
  "commission_eur": 0.0,
  "source": "onboarding_user_declaration",
  "universe_compliant": true
}
```

Cash positions go as a single trade event with `ticker: "CASH_EUR"`, `quantity: <amount>`, `unit_cost_eur: 1.0`.

### Step 4 — Initialize 6 paper portfolios

For each of `shadow`, `aggressive`, `conservative`, `value`, `momentum`, `quality`, create `data/events/portfolios/{portfolio_id}/trades.jsonl` with a single bootstrap event:

```json
{
  "event_type": "trade",
  "trade_kind": "portfolio_bootstrap",
  "ts": "<T0 ISO timestamp>",
  "trade_date": "<T0>",
  "ticker": "CASH_EUR",
  "quantity": 50000.0,
  "unit_cost_eur": 1.0,
  "portfolio_id": "<id>",
  "charter_immutable_at_t0": true,
  "source": "onboarding_bootstrap"
}
```

### Step 5 — Initialize `benchmark_passive`

Per CLAUDE.md §10, the benchmark is 70% iShares MSCI World Acc (IE00B4L5Y983), 20% Vanguard FTSE EM Acc (IE00B3VVMM84), 10% iShares € Govt Bond (IE00B4WXJJ64), nominal 50,000 €. Compute share quantities at T0 close prices from yfinance; persist three trade events with `trade_kind: "benchmark_initial_allocation"`.

### Step 6 — Write `.env` and decision log

- Append `SYSTEM_T0=<YYYY-MM-DD>` to `.env`.
- Append a single event to `data/events/decisions.jsonl`:
  ```json
  {"event_type": "system_bootstrap", "ts": "...", "t0": "<YYYY-MM-DD>",
   "portfolios_initialized": ["real", "shadow", "aggressive", "conservative", "value", "momentum", "quality", "benchmark_passive"],
   "real_portfolio_value_eur": <total>, "paper_starting_capital_eur": 50000}
  ```
- Append a run event to `data/events/runs.jsonl` (`agent: "coordinator"`, `command: "onboarding"`, `inputs_hash`, success).

### Step 7 — Compute initial snapshots

Trigger `src/portfolios/snapshot.py --all --date $SYSTEM_T0` to materialize `data/snapshots/{portfolio_id}/latest.json` for each of the 8 portfolios.

## Output to user (Spanish, concise)

A confirmation message that leads with the bottom line:

```
✅ Sistema inicializado. T0 = YYYY-MM-DD.

Cartera real: X posiciones, NAV inicial = XX.XXX €
Carteras paper (6 × 50.000 €): shadow, aggressive, conservative, value, momentum, quality
Benchmark passive: 50.000 € en 70% IWDA / 20% VFEM / 10% IEAG

Siguiente paso: ejecutar /daily-cycle para arrancar el ciclo operativo.
```

If any compliance warning was triggered in Step 2 (forbidden asset in `real`), include it explicitly before the confirmation: *"Atención: la posición X no cumple §6 del universo; queda registrada pero el sistema no propondrá rebalanceos sobre ella."*

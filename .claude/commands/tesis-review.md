---
name: tesis-review
description: Refresh the status of live theses. With no argument, reviews all theses whose last review is > 30 days old. With a ticker argument, reviews only that one. Pulls recent news, optionally re-runs fundamental analysis on material change, and marks each thesis as still_valid | needs_refresh | invalidated.
argument-hint: "[TICKER] (optional)"
---

# /tesis-review — Review live theses

You are the Coordinator. The user wants to check whether existing investment theses still hold given new evidence (news, fundamentals, time elapsed).

## Purpose

Keep the thesis corpus honest. Theses age: catalysts trigger or fade, fundamentals shift, the macro regime changes. Stale theses lead to stale decisions. This command is the system's periodic cleanup mechanism.

## Preconditions

1. At least one `thesis` event exists in `data/events/theses/`. If none, abort: *"No hay tesis vivas que revisar. Empieza por /tesis-new <TICKER>."*
2. System is initialized.

## Execution sequence

### Step 1 — Build the review scope

If `$1` is provided (single ticker):
- Read `data/events/theses/$1.jsonl`. If absent, abort: *"No existe tesis previa para $1. Empieza por /tesis-new $1."*
- Scope = `{$1}`.

If `$1` is empty:
- Enumerate all `data/events/theses/*.jsonl`.
- For each ticker, find the latest `thesis` event (most recent `point_in_time_date`).
- Compute `days_since_review = today - point_in_time_date`.
- Scope = tickers where `days_since_review > 30`. Limit to the top 10 by `days_since_review` if scope > 10 (the rest wait for next review cycle).

If scope is empty (no ticker > 30d), surface: *"Todas las tesis están al día (revisadas en últimos 30 días). Sin acción."* End command.

### Step 2 — For each ticker in scope, run the review subroutine

For each ticker, in series (not parallel — keeps the audit trail linear):

#### 2a — Pull recent news

Invoke `news-scanner` in ad-hoc mode for the ticker with lookback window = `days_since_review` (cap at 90 days). Collect all events at severity CRITICAL, HIGH, or MEDIUM.

#### 2b — Check invalidation criteria

Read the latest thesis's `would_falsify` array. For each falsifier criterion, decide deterministically (no LLM judgement) whether it has been triggered by the news events or by fundamental data shifts (use simple keyword/event-type matching defined in the thesis itself).

- If ANY falsifier is triggered → status = `invalidated`.
- If a news event of severity CRITICAL fired but no falsifier triggered → status = `needs_refresh` (the world moved materially even if invalidation criteria didn't trigger literally).
- If only MEDIUM/HIGH news with no falsifier trigger → status = `still_valid` but with `news_present: true` flag.
- If no material news and no fundamental change → status = `still_valid`.

#### 2c — Optionally refresh fundamentals

If status ∈ {`needs_refresh`, `invalidated`} AND last fundamentals refresh is > 90 days old:
- Invoke `fundamental-analyst` for a fresh thesis (this writes a new `thesis` event with new `point_in_time_date`).
- If the refreshed thesis has materially different `confidence_calibrated` (> ±0.15 vs prior) or different `recommendation`, flag for user attention.

For `still_valid` status, do NOT re-run fundamental-analyst — that would be churn without benefit.

#### 2d — Append review event

Append a `thesis_review` event to `data/events/theses/{ticker}.jsonl`:

```json
{
  "event_type": "thesis_review",
  "ts": "...",
  "ticker": "ASML",
  "prior_thesis_event_id": "...",
  "status": "still_valid | needs_refresh | invalidated",
  "news_events_observed_count": 3,
  "falsifier_triggered": null | "<falsifier text that fired>",
  "days_since_last_review": 45,
  "refresh_executed": true | false,
  "refreshed_thesis_event_id": null | "...",
  "inputs_hash": "sha256:..."
}
```

### Step 3 — Aggregate and decision log

Append a single `coordinator_decision` event to `data/events/decisions.jsonl` summarizing the review batch:

```json
{
  "event_type": "coordinator_decision",
  "command": "tesis-review",
  "ts": "...",
  "scope_tickers": ["ASML", "MSFT", ...],
  "results": {"still_valid": 5, "needs_refresh": 2, "invalidated": 1},
  "invalidated_tickers": ["INTC"]
}
```

Append a run event to `data/events/runs.jsonl`.

## Output to user (Spanish)

Tabular summary leading with action items:

```
📋 Revisión de tesis (N tickers en alcance).

🔴 INVALIDADAS (1):
- INTC: falsifier disparado el 2026-04-22 ("Net Debt / EBITDA > 1.5x"). Consultar /tesis-new INTC si quieres re-analizar desde cero.

🟡 REQUIEREN REFRESH (2):
- META: noticia CRITICAL del 2026-04-30 (FTC ruling). Tesis nueva ya generada, confianza pasó de 0.74 a 0.58. Revisar.
- NVDA: 45 días desde último refresh + caída -12% intradía hace 1 semana. Tesis refrescada, recomendación cambia de BUY a HOLD.

🟢 SIGUEN VIGENTES (5):
- ASML, MSFT, GOOGL, AMZN, AAPL: sin cambios materiales.

Próximo paso sugerido: /tesis-new INTC (si quieres reabrir) o /rebalance-propose real (si las tesis invalidadas afectan tu cartera real).
```

If the user passed a single ticker and the result is `still_valid` with no news, the output is one line: *"Tesis sobre TICKER sigue vigente. Última revisión hace N días. Sin cambios materiales."*

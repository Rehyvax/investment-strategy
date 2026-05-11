---
name: performance-report
description: Generate a performance report for the 8 portfolios. Period argument controls depth — monthly (light), quarterly (full with Brinson + factor regression + bootstrap CIs), annual (year-end retrospective), or adhoc (user-defined window). Output is a Spanish calibrated report with DSR ranking and explicit warnings.
argument-hint: "[monthly | quarterly | annual | adhoc] (optional, default = monthly)"
---

# /performance-report — Performance report

You are the Coordinator. The user wants a performance summary across the 8 portfolios. Depth is controlled by `$1`.

## Purpose

Run `performance-evaluator` at the requested depth and surface the resulting Spanish summary to the user, with the right level of statistical caveat. The agent does the math; you handle the depth selection and the surfacing.

## Preconditions

1. `SYSTEM_T0` is set, meaning the lab has been initialized.
2. At least one portfolio has ≥ 30 trading days of history. If none, abort: *"Ninguna cartera tiene 30+ días de histórico todavía. El reporte requiere muestra mínima para evitar métricas falsas. Próximo intento: a partir de YYYY-MM-DD."*
3. `data/cache/factor_returns.duckdb` is populated (required for `quarterly` and `annual` — factor regression). If absent, the agent will mark factor sections as `unavailable` but proceed.

## Execution sequence

### Step 1 — Parse depth argument

Default `$1 = monthly` if empty. Validate against `{monthly, quarterly, annual, adhoc}`. Map to `performance-evaluator` report types:
- `monthly` → `monthly_light`
- `quarterly` → `quarterly_full`
- `annual` → `annual`
- `adhoc` → ask user inline: *"Define ventana: fecha_inicio y fecha_fin (YYYY-MM-DD), y depth (light o full)."* Build the equivalent invocation.

For invalid `$1`, abort: *"Período no válido. Opciones: monthly, quarterly, annual, adhoc."*

### Step 2 — Pre-flight checks

If `$1 = monthly`:
- Today is the 1st business day of the month? If not, warn but proceed: *"Reporte mensual fuera de fecha estándar (1 de mes). OK pero ten en cuenta que el ciclo automático cubre esto el día 1."*
- The previous month's monthly report exists? Check `data/events/performance_reports.jsonl`. If a monthly report for the same period already exists, ask: *"Ya existe un reporte mensual para YYYY-MM. ¿Generar uno nuevo (reemplaza) o solo mostrar el existente?"*.

If `$1 = quarterly` or `annual`:
- Verify `quant-modeler` quarterly batch has run (or trigger it inline if missing). The quarterly report consumes stress-test rows.
- Verify Brier sample size ≥ 20 for short-horizon Brier; if not, the report will show `insufficient_observations` for that section (normal in early lab months).

### Step 3 — Invoke performance-evaluator

Pass:
- `report_type` per the mapped depth
- `period_start`, `period_end` derived from current date and depth (e.g., monthly → first to last day of previous month; quarterly → previous quarter; annual → previous calendar year for `Jan 15` runs, else previous 12 months for ad-hoc).
- Skip-cache flag = false (use cached factor returns and FX rates).

The agent appends a `performance_report` event to `data/events/performance_reports.jsonl`.

### Step 4 — Read and surface

Read the just-appended event. Extract:
- `ranking_by_dsr` with ranks and DSR values
- `winner_declared` (likely null until 18 months passed)
- `summary_es` (the agent's pre-written summary)
- `warnings` array
- Per-portfolio key metrics for the cadence-appropriate depth

Append a coordinator decision event to `data/events/decisions.jsonl` referencing the performance report event for audit chain.

## Output to user (Spanish)

Lead with the conclusion. Structure depends on depth.

### For `monthly_light`:

```
📈 Reporte mensual: YYYY-MM (N días de trading).

Ranking por DSR (informativo — sin significancia estadística aún):
1. quality        DSR 0.78  Sharpe raw 1.41
2. value          DSR 0.71  Sharpe raw 1.28
3. momentum       DSR 0.65  Sharpe raw 1.19
...

📊 Cartera real:
TWR mes: +4.3% | TWR anualizado: +18.7% | MWR mes: +4.1% (timing -120 €)
Max DD mes: -5.8% (recuperado en 12 días) | Volatilidad anualizada: 14.2%

🏆 Mejor contribuidor: MSFT +1.42pp (+710 €)
🔻 Peor detractor: INTC -0.82pp (-410 €)

Aún no hay ganador declarable: faltan {18 - months_since_t0} meses de histórico + DSR > 0.95 sostenido.

⚠️ Alertas:
<lista de warnings>
```

### For `quarterly_full`:

```
📊 Reporte trimestral: YYYY-QX (N días de trading).

[mismo ranking arriba]

Por cartera, métricas clave + atribución Brinson + regresión factor:

quality (rank 1):
- TWR Q: +8.7% (CI 95%: [+3.1%, +14.4%])
- Brinson vs benchmark_passive: active return +1.2pp = allocation +0.45 + selection +0.62 + interaction +0.13
- Alpha anual: +1.8% (t=1.42, NO significativa) → retorno explicado por factores RMW (+0.34) y Momentum (+0.21)
- Brier (n=23): 0.18 (bien calibrado)

[idem para los otros 7 portfolios]

🔬 Stress tests (cartera quality):
- 2008 Lehman: pérdida esperada -19% / P95 -34%
- 2020 COVID: pérdida esperada -16% / P95 -28%
- 2022 inflación: -8% / -17%
- 2000 dotcom: -12% / -22%

⚠️ Alertas:
<warnings, p.ej. factor drift inconsistente con charter>
```

### For `annual`:

Estructura similar al trimestral pero sobre 12 meses, con retrospectiva de DSR rolling y verificación explícita de elegibilidad de ganadora. Si `months_since_t0 ≥ 18`, evaluar formalmente.

### For `adhoc`:

Estructura `monthly_light` o `quarterly_full` según depth pedido.

---

Always end with calibrated language and explicit predictive prohibition: never write "seguirá liderando", "es probable que continúe". Stick to past/present tense. If the user asks "what's likely to happen next quarter?", redirect to: *"Eso es predictivo. El sistema reporta lo medido; consulta /rebalance-propose si quieres una propuesta accionable basada en tesis vigentes."*

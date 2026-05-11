---
name: modelo-720-check
description: Annual verification of Modelo 720 reporting obligation. Computes year-end (Dec 31 prior year) totals of foreign-custodied securities and cash in the real portfolio, classifies by AEAT category (V/I/C), compares against §1.6 thresholds, and surfaces a Spanish summary with submission-ready totals if applicable.
---

# /modelo-720-check — Modelo 720 obligation check

You are the Coordinator. The user wants to know whether they must file Modelo 720 this year and, if so, with what content. Always concerns the `real` portfolio (paper portfolios have no tax reality).

## Purpose

Surface the Modelo 720 obligation status for the prior calendar year, with category-classified totals ready for telematic submission via AEAT Sede Electrónica. Compliant with `rebalancing-tax` §1.6 and DGT V1013-25.

## Preconditions

1. `SYSTEM_T0` set; `real` portfolio exists.
2. `real` portfolio has snapshots covering Dec 31 of the prior year (or the closest preceding trading day).
3. Today's date logic:
   - The filing window is January 1 – March 31 each year.
   - The command is callable any day of the year, but warns if invoked outside the filing window:
     *"Fecha actual fuera de la ventana de declaración (1 enero – 31 marzo). El reporte sirve igualmente como verificación, pero la presentación efectiva en AEAT es entre esas fechas."*

## Execution sequence

### Step 1 — Resolve target year

The target year is `prior_calendar_year` (e.g., if today is 2026-05-11, the relevant year is 2025). For the `Dec 31` snapshot, use `data/snapshots/real/{YYYY}-12-31.json` if it exists, otherwise the latest snapshot before Dec 31 of the target year.

If no snapshot of `real` exists for that date or any preceding date in the target year, abort: *"No hay snapshot de la cartera real para 31-12-{YYYY}. Re-ejecuta /daily-cycle al menos una vez antes de esa fecha en el futuro; o ingesta el CSV de Lightyear de cierre de año vía /ingest-lightyear-csv."*

### Step 2 — Invoke rebalancing-tax in compliance mode

Pass:
- `mode: "compliance"`
- `target_date: {YYYY}-12-31`
- `target_portfolio: real`

The agent will:
1. Read the Dec 31 snapshot of `real`.
2. Compute total value of foreign-custodied securities + cash in EUR using the Dec 31 ECB FX rates.
3. Classify each position into one of three AEAT categories per §1.6:
   - **Class V**: single equities (`valores representativos de la cesión a terceros…`)
   - **Class I**: UCITS ETFs (`participaciones en IIC`) per DGT V1013-25
   - **Class C**: cash and MMF Vault balances (`cuentas`)
4. Compare against prior-year filing (read from `data/state/modelo_720_history.jsonl` if it exists).
5. Determine obligation status:
   - `must_file_first_time`: never filed before AND total > 50,000 €
   - `must_file_increment`: filed before AND any class block increased > 20,000 €
   - `must_file_threshold`: filed before AND total still > 50,000 € but no class crossed the 20k delta (still required)
   - `not_required`: total < 50,000 € AND no class crossed delta
6. Append a `compliance_assessment` event to `data/events/compliance_assessments.jsonl`.

### Step 3 — Modelo D-6 sanity check

The agent also performs the D-6 check explicitly (per CLAUDE.md §7.6 and `rebalancing-tax` §1.7). For each holding, verify that the user does not own ≥ 10% of the issuer's capital. With ~50k€ across diversified mid/large caps this is impossible to hit, but the documented check prevents future unfounded concern. Surface the confirmation in the output even when negative.

### Step 4 — Persist coordinator decision

Append a `coordinator_decision` event to `data/events/decisions.jsonl`:

```json
{
  "event_type": "coordinator_decision",
  "command": "modelo-720-check",
  "ts": "...",
  "target_year": 2025,
  "snapshot_date_used": "2025-12-31",
  "compliance_assessment_event_id": "...",
  "obligation_status": "must_file_first_time | must_file_increment | must_file_threshold | not_required",
  "submission_window_active": true | false
}
```

And a run event to `data/events/runs.jsonl`.

### Step 5 — Optional history append (if user files)

After the user actually files Modelo 720 (manual step in AEAT Sede Electrónica), they will run this command again with a follow-up. For now, do NOT auto-append to `data/state/modelo_720_history.jsonl` — that file records *filed* declarations, not *prepared* ones. The user updates it manually post-filing (a future `/modelo-720-mark-filed` command, not part of v1).

## Output to user (Spanish)

Lead with the obligation status. Format:

### Case A — `not_required`:

```
🇪🇸 Modelo 720 — año fiscal 2025

Obligación: NO requerido este año.

Motivo:
- Valor total a 31-12-2025 de la cartera real (clase V+I+C): XX.XXX,XX €
- Umbral: 50.000 € (no superado)
- Sin incremento > 20.000 € vs declaración anterior (no aplica, sin historial)

Modelo D-6: no aplicable (todas las posiciones < 10% del capital de su emisor — confirmado).

Sin acción requerida. La obligación se reevalúa cada enero automáticamente.
```

### Case B — `must_file_first_time` or `must_file_*`:

```
🇪🇸 Modelo 720 — año fiscal 2025

Obligación: DECLARACIÓN REQUERIDA (motivo: <razón concreta>).

Plazo: 1 enero 2026 – 31 marzo 2026 [hoy es YYYY-MM-DD, dentro del plazo | quedan N días].

Totales a 31-12-2025 (cartera real, custodia Lightyear Europe AS / Lightyear UK Ltd):

Clase V (valores representativos — acciones individuales):
- MSFT 10 acciones: XX.XXX,XX €
- ASML 3 acciones:   X.XXX,XX €
- ...
- TOTAL clase V:    XX.XXX,XX €

Clase I (IIC — UCITS ETFs):
- IWDA 25 partes:    X.XXX,XX €
- ...
- TOTAL clase I:    XX.XXX,XX €

Clase C (cuentas y MMF Vault):
- Cash EUR Vault:    X.XXX,XX €
- TOTAL clase C:     X.XXX,XX €

TOTAL DECLARADO:    XX.XXX,XX €
(incremento vs año anterior: +X.XXX,XX €)

Custodio único: Lightyear Europe AS (Estonia) | Lightyear UK Ltd (UK) — un único depositario en sentido formal.

Modelo D-6: no aplicable (todas posiciones < 10% del emisor — confirmado).

📋 Siguientes pasos:
1. Acceder a AEAT Sede Electrónica → Modelo 720
2. Identificarse con Cl@ve o certificado digital
3. Introducir cada posición usando la clave correspondiente (V/I/C)
4. Datos del depositario: Lightyear Europe AS, dirección Tallinn (Estonia) — verifica los datos exactos en tu extracto Lightyear
5. Presentar telemáticamente antes del 31-03-2026
```

### Always end with:

*"Esta verificación es técnica, no asesoramiento fiscal. Para casos límite o primera declaración, consulta con un asesor fiscal autorizado."*

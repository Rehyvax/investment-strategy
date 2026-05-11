# Investment Strategy Lab

> Laboratorio de paper-trading multi-agente para investigación y gestión de cartera medio-largo plazo, residente fiscal en España, broker Lightyear.

---

## 1. Qué es esto en una frase

Un sistema que **te ayuda a decidir** qué hacer con tus 50.000 € en Lightyear:
genera tesis fundamentales, evalúa riesgo y fiscalidad, y hace correr en paralelo
**8 carteras competidoras** para descubrir empíricamente qué estrategia funciona mejor.

**El sistema nunca ejecuta operaciones reales.** Tú decides, tú haces clic en Lightyear.

---

## 2. ¿Qué NO es?

- ❌ No es un robot de trading. No ejecuta nada.
- ❌ No promete rentabilidades. Lleva la cuenta de cómo se equivoca (Brier, DSR).
- ❌ No te dice "compra mañana a las 10:32". Habla en probabilidades sobre meses.
- ❌ No reemplaza a un asesor fiscal. Modela las reglas del IRPF pero no las certifica.

---

## 3. Las 8 carteras competidoras

Todas arrancan con **50.000 € en T0** (día de bootstrap) y corren en lockstep
bajo mandatos **inmutables**.

| Cartera | Mandato resumido |
|---|---|
| `real` | Espejo de tu Lightyear. Solo se actualiza al importar CSV. |
| `shadow` | Lo que el sistema recomendaría. Diverge de `real` cuando no ejecutas. |
| `aggressive` | Mean-variance max-Sharpe + momentum. Hasta 12 posiciones. |
| `conservative` | Risk Parity, ≤8 % por activo, ≥20 % en MMF/bonos corto plazo. |
| `value` | Top-15 valor + Piotroski ≥7, equiponderado. |
| `momentum` | Top decil de retorno 12m-1m, top 20, equiponderado. |
| `quality` | ROIC > WACC sostenido 5 años, pesos HRP, 15-20 posiciones. |
| `benchmark_passive` | 70 % MSCI World + 20 % EM + 10 % bonos €. |

> **Regla de inmutabilidad**: un charter NO se modifica nunca tras T0.
> Si una estrategia debe evolucionar, se crea `quality_v2` y la vieja sigue corriendo
> para comparación histórica.

---

## 4. Primeros pasos (una sola vez)

### 4.1 Instala `uv` (gestor de Python)

```powershell
# PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

### 4.2 Crea tu archivo de secretos

```powershell
copy .env.example .env
notepad .env
```

Rellena al menos `FRED_API_KEY` (gratis en https://fred.stlouisfed.org).
Los demás (FMP, Finnhub, Alpha Vantage) son opcionales pero recomendados.

### 4.3 Instala dependencias

```powershell
uv sync
```

Esto crea un `.venv/` local con todas las librerías. Reproducible vía `uv.lock`.

### 4.4 Bootstrap del laboratorio

Cuando los sub-agentes estén creados (sesiones siguientes), abre Claude Code
en este directorio y pídele:

> "Ejecuta el checklist de bootstrap del §15 de CLAUDE.md."

El sistema verificará la estructura, te pedirá tus posiciones actuales de Lightyear,
e inicializará las 6 carteras competidoras con 50.000 € cada una.

---

## 5. El día a día como operador

| Cuándo | Qué pides al sistema | Qué te devuelve |
|---|---|---|
| **Diario** | "¿Algo importante en mis posiciones?" | Alertas sobre movimientos > 5 %, earnings, downgrades. |
| **Lunes** | "Revisión semanal." | Estado de las 8 carteras + propuestas de ajuste. |
| **1 del mes** | "Informe mensual." | TWR, atribución Brinson, calibración Brier, refresh de tesis. |
| **Cada idea** | "Analiza $TICKER." | Tesis completa + valoración + riesgo + fiscalidad + veredicto. |
| **Trimestral** | "Revisión profunda." | Ranking DSR, regresiones factoriales, auditoría aleatoria. |
| **15 enero** | (Automático) | Recordatorio Modelo 720 + oportunidades de tax-loss harvesting. |

**Comunicación**: respuestas en español, **conclusión primero**, legible en 60 segundos.
Si quieres profundizar, pides el desglose.

---

## 6. Reglas fiscales que el sistema aplica automáticamente

1. **IRPF base del ahorro 2026**: tramos 19/21/23/27/30 %.
2. **Regla de los 2 meses** (art. 33.5 f LIRPF): si vendes con pérdida y recompras
   el mismo ISIN en ±2 meses, la pérdida se difiere. El sistema simula esto
   ANTES de proponer cualquier rebalance o cosecha de pérdidas.
3. **Retención dividendos USA**: 15 % con W-8BEN firmado en Lightyear,
   recuperable como deducción por doble imposición.
4. **ETFs**: no hay traspaso fiscal-neutro entre ETFs en España.
   Preferencia **siempre** por ETFs UCITS de **acumulación** (Acc) sobre distribución.
5. **Modelo 720**: aviso automático cada 15 de enero. Lightyear es custodia extranjera.
6. **Modelo D-6**: no aplica (eres minorista con <10 % de cualquier emisor).

---

## 7. Universo permitido

- ✅ Acciones individuales en NYSE, NASDAQ, LSE, Xetra, Euronext, BME, SIX, Borsa Italiana, Nasdaq Baltic.
- ✅ ETFs UCITS (ISIN `IE…` o `LU…`) con KID PRIIPs.
- ✅ MMF (cash) vía Vaults de Lightyear.

- ❌ ETFs USA (SPY, VOO, QQQ…): bloqueados por PRIIPs.
- ❌ Derivados, apalancamiento, cortos, ETFs apalancados/inversos.
- ❌ Crypto.
- ❌ Penny stocks, OTC, micro-caps con ADV < 1 M€.

---

## 8. Estructura del proyecto

```
investment-strategy/
├── CLAUDE.md             ← Constitución del Coordinador (no toques sin pensar)
├── README.md             ← Este archivo
├── pyproject.toml        ← Dependencias Python (gestionadas con uv)
├── .env                  ← Tus secretos (NO se sube nunca a git)
├── .env.example          ← Plantilla de .env
├── .claude/
│   ├── agents/           ← Sub-agentes especializados (se diseñan uno a uno)
│   └── commands/         ← Slash commands para el operador
├── data/                 ← LOCAL, nunca en git
│   ├── events/           ← JSONL append-only (fuente de verdad)
│   ├── snapshots/        ← Estado derivado regenerable
│   ├── memory/           ← Memoria curada por agente
│   ├── audit/            ← Bundles content-addressed
│   ├── inbox/lightyear/  ← Aquí dejas los CSV exportados de Lightyear
│   └── cache.duckdb      ← Caché analítica regenerable
├── src/                  ← Código Python (inglés, comentarios densos)
└── docs/                 ← Material de referencia sin PII
```

> Si pierdes `data/cache.duckdb`, `data/snapshots/`, o cualquier cosa derivada,
> **no pasa nada**: se regenera desde los JSONL en `data/events/`.
>
> Si pierdes `data/events/`, **pierdes la historia**. Haz backup de esa carpeta.

---

## 9. Filosofía de persistencia (importante)

- **JSONL append-only** = fuente de verdad inmutable. Una vez escrito un evento,
  no se edita nunca. Si un dato cambia, se **añade un evento de corrección**
  con timestamp nuevo. Esto evita look-ahead bias y permite auditar cualquier
  decisión histórica.
- **DuckDB** = caché analítica. Se reconstruye en segundos desde los JSONL.
- **Snapshots JSON** = comodidad de lectura para la UI.

---

## 10. Cuándo desconfiar del sistema

El sistema lleva un score de calibración (**Brier**) sobre todas sus predicciones.
Si su Brier sube por encima de 0,25 durante 3 meses seguidos: **está mal calibrado**,
trátalo como una segunda opinión, no como una primera.

Igualmente, el `red-team` audita cualquier propuesta material antes de llegarte.
Si el red-team y el resto de agentes no logran reconciliarse, el sistema te
presenta **ambos lados** explícitamente — tú decides.

---

## 11. Qué hago yo (operador) y qué hace Claude Code

| Tú | Claude Code |
|---|---|
| Ejecutas operaciones reales en Lightyear | Genera propuestas razonadas |
| Importas CSV de Lightyear al `inbox/` | Parsea CSV → actualiza cartera `real` |
| Confirmas cambios de mandato (con `/mandate-change`) | Bloquea cambios en charters >30 días |
| Backup de `data/events/` | Mantiene el JSONL sano y auditable |
| Decisión final | Análisis, valoración, riesgo, fiscalidad |

---

## 12. Próximos pasos

Esta sesión solo ha creado **la estructura**. Pendiente:

1. ✅ Estructura de directorios.
2. ✅ `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`.
3. ⏳ Diseñar los 8 sub-agentes en `.claude/agents/` (uno por uno, con cuidado).
4. ⏳ Implementar `src/ingestion/lightyear_csv.py` para importar tu cartera real.
5. ⏳ Implementar `src/portfolios/cost_model.py` con el modelo de costes de Lightyear.
6. ⏳ Bootstrap §15: inicializar las 6 carteras competidoras a T0.
7. ⏳ Primer ciclo semanal de prueba con cartera real.

---

*Última revisión: bootstrap. Documento en español, operativo para el usuario.*

# Investment Dashboard

Mobile-first dashboard for personal portfolio management. Built with
Streamlit. Phase 2A includes **Pantalla 1 — Home Cockpit** (6 blocks:
market status, portfolio summary, tax alerts, multi-portfolio chart,
top-3 recommendations, comparative analysis, news feed).

## Local development

```bash
cd dashboard
pip install -r requirements.txt
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml: replace REPLACE_WITH_* with real tokens.
streamlit run app.py
```

The app opens at <http://localhost:8501>. Without a `secrets.toml`,
the dashboard runs in dev-mode (anyone can access) with a visible
warning at the top.

## Deploy to Streamlit Cloud (free)

1. Push this repo to GitHub (already wired to `Rehyvax/investment-strategy`).
2. Sign in to <https://streamlit.io/cloud> with GitHub.
3. **New app** → select this repo, branch `main`.
4. **Main file path**: `dashboard/app.py`
5. **Advanced settings → Secrets**: paste the contents of your local
   `.streamlit/secrets.toml`. Streamlit Cloud reads them at runtime.
6. **Deploy**. URL will be `https://<app-name>.streamlit.app`.
7. Share the gated URL with trusted recipients as:
   `https://<app-name>.streamlit.app/?token=<one of valid_tokens>`.

## Architecture

```
dashboard/
├── app.py                      Streamlit entry; auth + sidebar.
├── auth.py                     URL-token auth (retail-grade).
├── pages/
│   └── 1_Home.py               Pantalla 1 — Home Cockpit.
├── services/
│   ├── cerebro_state.py        Loads the mock cerebro JSON.
│   ├── snapshot_reader.py      Reads data/snapshots/*.json.
│   ├── events_reader.py        Reads data/events/*.jsonl.
│   └── price_log_reader.py     Thin wrapper over PriceLog.
├── components/
│   ├── market_status.py        Block A — regime + flow + fear.
│   ├── portfolio_summary.py    Block B — NAV + deltas + health.
│   ├── tax_alerts.py           Block B' — LIRPF 2-month rule.
│   ├── multi_portfolio_chart.py Block C — 9-portfolio chart.
│   ├── recommendations.py      Block D — top-3 recommendations.
│   ├── comparative.py          Block E — comparative analysis.
│   └── news_feed.py            Block F — news filtered by holdings.
├── data/
│   └── cerebro_state.json      Mock cerebro output. Replaced in
│                                Phase 2B by a daily cron that
│                                invokes Anthropic API.
├── .streamlit/
│   ├── config.toml             Theme + server config.
│   └── secrets.toml.template   Auth tokens template (not the real one).
├── requirements.txt
└── tests/
    ├── test_auth.py
    └── test_components.py
```

## Cost model (production)

| Item | Cost / month |
|---|---:|
| Streamlit Cloud | free |
| Anthropic API (cerebro daily + chat ad-hoc, Phase 2B) | ~$8–15 |
| **Total** | **~$10** |

## Design principles (applied across all screens)

1. **Opinión honesta directa.** No scores, no multiple choice. The
   cerebro commits ("MSFT sólida → subir de 6.9% a 9% NAV, €1,000").
2. **Análisis matizado.** Falsifiers are NOT binary triggers — the
   cerebro weighs them against macro and news.
3. **Cerebro pondera conjunto.** No single factor decides.

## Tests

```bash
pip install pytest
pytest dashboard/tests/ -v
```

Uses `streamlit.testing.v1.AppTest` (smoke tests, no browser required).

## Phase 2B (next)

- **Pantalla 5** — Comparativa Portfolios (full ranking + delta toggles).
- **Cerebro generator** — daily cron invoking Anthropic API to write
  `data/cerebro_state.json` from snapshots + events.
- **Chat ad-hoc** — per-recommendation "Preguntar más" wired to API.

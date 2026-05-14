@echo off
REM ===========================================================
REM Auto-commit cerebro_state.json to public repo (Streamlit Cloud).
REM
REM Cron entries:
REM   Investment_Auto_Commit_Morning    Mon-Fri 08:35 (post-cerebro daily)
REM   Investment_Auto_Commit_Afternoon  Mon-Fri 15:45 (post-Claude Autonomous)
REM
REM Both jobs are gated by tests/test_pii_safety.py — if any pattern
REM matches the cerebro JSON, the commit is aborted with non-zero exit.
REM ===========================================================
setlocal

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

if not exist logs mkdir logs

set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\auto_commit_cerebro.log
echo === %date% %time% START === >> logs\auto_commit_cerebro.log

REM ---- Safety gate: PII regression -----------------------------------
"%PY%" -m pytest tests/test_pii_safety.py -q >> logs\auto_commit_cerebro.log 2>&1
if errorlevel 1 (
    echo [%date% %time%] PII test FAILED — aborting commit >> logs\auto_commit_cerebro.log
    echo === %date% %time% END (PII abort) === >> logs\auto_commit_cerebro.log
    exit /b 1
)

REM ---- Stage all PII-gated Cloud artifacts --------------------------
REM   - cerebro_state.json        (always present after cron)
REM   - snapshot_real_latest.json (added Fase 6E, may be absent on fresh
REM     checkouts before the first cron run)
REM   - dashboard_bundle.json     (added Fase 6E, same caveat)
REM All three are gated by tests/test_pii_safety.py above. `if exist`
REM guards prevent failures on fresh repos.
git add dashboard/data/cerebro_state.json >> logs\auto_commit_cerebro.log 2>&1
if exist dashboard\data\snapshot_real_latest.json (
    git add dashboard/data/snapshot_real_latest.json >> logs\auto_commit_cerebro.log 2>&1
)
if exist dashboard\data\dashboard_bundle.json (
    git add dashboard/data/dashboard_bundle.json >> logs\auto_commit_cerebro.log 2>&1
)

REM ---- Skip the commit if the file content didn't change -------------
git diff --cached --quiet
if errorlevel 1 (
    REM Build a date stamp YYYY-MM-DD via PowerShell (locale-safe)
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"`) do set TODAY=%%I

    git commit -m "Auto: cerebro state update %TODAY%" >> logs\auto_commit_cerebro.log 2>&1
    if errorlevel 1 (
        echo [%date% %time%] Commit FAILED >> logs\auto_commit_cerebro.log
        echo === %date% %time% END (commit fail) === >> logs\auto_commit_cerebro.log
        exit /b 1
    )

    git push origin main >> logs\auto_commit_cerebro.log 2>&1
    if errorlevel 1 (
        echo [%date% %time%] Push FAILED >> logs\auto_commit_cerebro.log
        echo === %date% %time% END (push fail) === >> logs\auto_commit_cerebro.log
        exit /b 1
    )

    echo [%date% %time%] Auto-commit success >> logs\auto_commit_cerebro.log
) else (
    echo [%date% %time%] No changes to commit >> logs\auto_commit_cerebro.log
)

echo === %date% %time% END (exit 0) === >> logs\auto_commit_cerebro.log
exit /b 0

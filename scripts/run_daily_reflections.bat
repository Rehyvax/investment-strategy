@echo off
REM Daily reflection runner — measures realized vs predicted return for
REM debates from 7 days ago. Idempotent.
REM Cron: weekdays 08:30 (after Cerebro Generation @ 08:00).

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

if not exist logs mkdir logs

set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\daily_reflections_cron.log
echo === %date% %time% START === >> logs\daily_reflections_cron.log
"%PY%" scripts\run_daily_reflections.py >> logs\daily_reflections_cron.log 2>&1
echo === %date% %time% END (exit %ERRORLEVEL%) === >> logs\daily_reflections_cron.log
exit /b %ERRORLEVEL%

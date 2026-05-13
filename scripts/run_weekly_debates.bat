@echo off
REM Weekly Bull/Bear debate runner.
REM Invoked by Windows Task Scheduler (Mondays 09:00). For ad-hoc runs
REM call: python scripts\run_weekly_debates.py [--force --ticker MSFT]

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

if not exist logs mkdir logs

set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\weekly_debates_cron.log
echo === %date% %time% START === >> logs\weekly_debates_cron.log
"%PY%" scripts\run_weekly_debates.py >> logs\weekly_debates_cron.log 2>&1
echo === %date% %time% END (exit %ERRORLEVEL%) === >> logs\weekly_debates_cron.log
exit /b %ERRORLEVEL%

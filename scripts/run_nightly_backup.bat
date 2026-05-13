@echo off
REM Nightly data backup runner.
REM Cron: every day 23:00 (Mon-Sun). Cleanup retention: 30 days.

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

if not exist logs mkdir logs

set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\backup_nightly_cron.log
echo === %date% %time% START === >> logs\backup_nightly_cron.log
"%PY%" scripts\backup_nightly.py >> logs\backup_nightly_cron.log 2>&1
echo === %date% %time% END (exit %ERRORLEVEL%) === >> logs\backup_nightly_cron.log
exit /b %ERRORLEVEL%

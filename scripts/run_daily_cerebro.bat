@echo off
REM Daily cerebro state regeneration.
REM Invoked by the Windows Task Scheduler entry created by
REM scripts/install_daily_task.ps1. Logs to logs/cerebro_daily.log.

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

REM Ensure logs directory exists (no-op if already there).
if not exist logs mkdir logs

REM Use the project venv Python if present; fall back to system Python.
set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\cerebro_daily.log
echo === %date% %time% START === >> logs\cerebro_daily.log
"%PY%" scripts\generate_cerebro_state.py >> logs\cerebro_daily.log 2>&1
echo === %date% %time% END (exit %ERRORLEVEL%) === >> logs\cerebro_daily.log
exit /b %ERRORLEVEL%

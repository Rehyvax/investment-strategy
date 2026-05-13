@echo off
REM Daily news scanner runner.
REM Invoked by the Windows Task Scheduler entry created by
REM scripts/install_daily_task.ps1 (Mon-Fri 07:30). Skips weekends in
REM Python so a manual run on Sat/Sun still no-ops cleanly.

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

if not exist logs mkdir logs

set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\news_scanner_daily.log
echo === %date% %time% START === >> logs\news_scanner_daily.log
"%PY%" scripts\news_scanner.py >> logs\news_scanner_daily.log 2>&1
echo === %date% %time% END (exit %ERRORLEVEL%) === >> logs\news_scanner_daily.log
exit /b %ERRORLEVEL%

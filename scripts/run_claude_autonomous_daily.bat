@echo off
REM Claude Autonomous daily runner.
REM Cron: weekdays 15:30 ES (post US-market open at 15:30 CET / 09:30 ET).
REM Coste estimado por run: ~$0.50-1.50 LLM + free Alpaca paper.

set PROJECT_DIR=C:\Users\Lluis\Documents\investment-strategy
cd /d %PROJECT_DIR%

if not exist logs mkdir logs

set PY=%PROJECT_DIR%\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo. >> logs\claude_autonomous_cron.log
echo === %date% %time% START === >> logs\claude_autonomous_cron.log
"%PY%" scripts\run_claude_autonomous_daily.py >> logs\claude_autonomous_cron.log 2>&1
echo === %date% %time% END (exit %ERRORLEVEL%) === >> logs\claude_autonomous_cron.log
exit /b %ERRORLEVEL%

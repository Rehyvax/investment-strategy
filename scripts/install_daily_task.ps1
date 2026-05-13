# install_daily_task.ps1
# Run as Administrator.
#
# Creates (or replaces) the Windows Scheduled Tasks for the
# investment lab daily automation:
#
#   Investment_News_Scan_Daily       Mon-Fri 07:30  news_scanner.py
#   Investment_Cerebro_Daily         Mon-Fri 08:00  generate_cerebro_state.py
#   Investment_Reflections_Daily     Mon-Fri 08:30  run_daily_reflections.py
#   Investment_Nightly_Backup        Daily   23:00  backup_nightly.py
#
# The 30-min gaps between morning tasks let earlier tasks finish before
# downstream consumers run. The nightly backup runs Mon-Sun (data
# changes during weekends are rare but worth preserving).
#
# DELIBERATELY NOT installed: the weekly Bull/Bear debate sweep.
# Spend (~$3-4 per full sweep on 19 positions) is gated behind the
# manual "Ejecutar barrido semanal" button in the dashboard sidebar,
# which shows the cost estimate and requires explicit confirmation.
# Reflections still mature naturally on whatever debates the user
# triggers manually (or via news_high triggers when they hit the
# button).
#
# If you previously installed Investment_Weekly_Debates, this script
# does NOT remove it. Run:
#   Unregister-ScheduledTask -TaskName "Investment_Weekly_Debates" -Confirm:$false
# once to clean up.
#
# Usage:
#   PowerShell (Admin) -> cd C:\Users\Lluis\Documents\investment-strategy
#   powershell.exe -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1

$PROJECT = "C:\Users\Lluis\Documents\investment-strategy"

function Install-WeeklyTask {
    param(
        [string]$Name,
        [string]$BatPath,
        [string]$AtTime,
        [string]$Description,
        [string[]]$Days
    )
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    $Action  = New-ScheduledTaskAction -Execute $BatPath
    $Trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek $Days `
        -At $AtTime
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable
    Register-ScheduledTask `
        -TaskName $Name `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description $Description | Out-Null
    $dayList = ($Days -join ",")
    Write-Host "Task '$Name' created ($dayList $AtTime)."
}

$weekdays = @("Monday","Tuesday","Wednesday","Thursday","Friday")

Install-WeeklyTask `
    -Name "Investment_News_Scan_Daily" `
    -BatPath "$PROJECT\scripts\run_daily_news_scanner.bat" `
    -AtTime "7:30am" `
    -Days $weekdays `
    -Description "Daily multi-source news scan + LLM relevance scoring."

Install-WeeklyTask `
    -Name "Investment_Cerebro_Daily" `
    -BatPath "$PROJECT\scripts\run_daily_cerebro.bat" `
    -AtTime "8:00am" `
    -Days $weekdays `
    -Description "Daily cerebro state regeneration (consumes news+technicals+fundamentals+debates)."

Install-WeeklyTask `
    -Name "Investment_Reflections_Daily" `
    -BatPath "$PROJECT\scripts\run_daily_reflections.bat" `
    -AtTime "8:30am" `
    -Days $weekdays `
    -Description "Daily reflection loop — realized vs predicted for debates from 7d ago."

# NOTE: Investment_Weekly_Debates is intentionally not installed.
# Use the dashboard sidebar 'Ejecutar barrido semanal' button to
# trigger the full sweep on demand with cost confirmation.

# Nightly backup runs every day (Mon-Sun) — uses a Daily trigger,
# not the Weekly helper above.
Unregister-ScheduledTask -TaskName "Investment_Nightly_Backup" -Confirm:$false -ErrorAction SilentlyContinue
$BackupAction = New-ScheduledTaskAction -Execute "$PROJECT\scripts\run_nightly_backup.bat"
$BackupTrigger = New-ScheduledTaskTrigger -Daily -At "23:00"
$BackupSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
Register-ScheduledTask `
    -TaskName "Investment_Nightly_Backup" `
    -Action $BackupAction `
    -Trigger $BackupTrigger `
    -Settings $BackupSettings `
    -Description "Nightly zip backup of data/ + dashboard/data + MEMORY.md (30d retention)." | Out-Null
Write-Host "Task 'Investment_Nightly_Backup' created (Daily 23:00)."

Write-Host ""
Write-Host "Manual run:    Start-ScheduledTask -TaskName 'Investment_News_Scan_Daily'"
Write-Host "Inspect all:   Get-ScheduledTask -TaskName 'Investment_*' | Format-List *"
Write-Host "Remove all:    Unregister-ScheduledTask -TaskName 'Investment_*' -Confirm:`$false"

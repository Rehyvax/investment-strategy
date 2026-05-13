# install_daily_task.ps1
# Run as Administrator.
#
# Creates (or replaces) the Windows Scheduled Tasks for the
# investment lab daily/weekly automation:
#
#   Investment_News_Scan_Daily       Mon-Fri 07:30  news_scanner.py
#   Investment_Cerebro_Daily         Mon-Fri 08:00  generate_cerebro_state.py
#   Investment_Reflections_Daily     Mon-Fri 08:30  run_daily_reflections.py
#   Investment_Weekly_Debates        Mon       09:00  run_weekly_debates.py
#
# The 30-min gaps let earlier tasks finish before downstream consumers
# run. Reflections need debates from ~7 days ago to be present, so the
# weekly debate job must run before the reflection job catches up.
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

Install-WeeklyTask `
    -Name "Investment_Weekly_Debates" `
    -BatPath "$PROJECT\scripts\run_weekly_debates.bat" `
    -AtTime "9:00am" `
    -Days @("Monday") `
    -Description "Weekly Bull/Bear debate cycle for all real-portfolio positions."

Write-Host ""
Write-Host "Manual run:    Start-ScheduledTask -TaskName 'Investment_News_Scan_Daily'"
Write-Host "Inspect all:   Get-ScheduledTask -TaskName 'Investment_*' | Format-List *"
Write-Host "Remove all:    Unregister-ScheduledTask -TaskName 'Investment_*' -Confirm:`$false"

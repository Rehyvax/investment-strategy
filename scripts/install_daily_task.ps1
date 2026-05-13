# install_daily_task.ps1
# Run as Administrator.
#
# Creates (or replaces) two Windows Scheduled Tasks:
#   - Investment_News_Scan_Daily    Mon-Fri 07:30  (news_scanner.py)
#   - Investment_Cerebro_Daily      Mon-Fri 08:00  (generate_cerebro_state.py)
#
# The 30-minute gap lets the scanner finish (~1-3 min for 19 tickers
# with LLM scoring) so the cerebro generator reads fresh news.
#
# Usage:
#   PowerShell (Admin) -> cd C:\Users\Lluis\Documents\investment-strategy
#   powershell.exe -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1

$PROJECT = "C:\Users\Lluis\Documents\investment-strategy"

function Install-DailyTask {
    param(
        [string]$Name,
        [string]$BatPath,
        [string]$AtTime,
        [string]$Description
    )
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    $Action  = New-ScheduledTaskAction -Execute $BatPath
    $Trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
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
    Write-Host "Task '$Name' created (Mon-Fri $AtTime)."
}

Install-DailyTask `
    -Name "Investment_News_Scan_Daily" `
    -BatPath "$PROJECT\scripts\run_daily_news_scanner.bat" `
    -AtTime "7:30am" `
    -Description "Daily multi-source news scan + LLM relevance scoring."

Install-DailyTask `
    -Name "Investment_Cerebro_Daily" `
    -BatPath "$PROJECT\scripts\run_daily_cerebro.bat" `
    -AtTime "8:00am" `
    -Description "Daily cerebro state regeneration (consumes news+technicals+fundamentals)."

Write-Host ""
Write-Host "Run manually:  Start-ScheduledTask -TaskName 'Investment_News_Scan_Daily'"
Write-Host "Run manually:  Start-ScheduledTask -TaskName 'Investment_Cerebro_Daily'"
Write-Host "Inspect:       Get-ScheduledTask -TaskName 'Investment_*' | Format-List *"
Write-Host "Remove:        Unregister-ScheduledTask -TaskName 'Investment_*' -Confirm:`$false"

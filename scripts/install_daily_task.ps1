# install_daily_task.ps1
# Run as Administrator.
#
# Creates (or replaces) a Windows Scheduled Task that regenerates the
# cerebro state every weekday at 08:00 by invoking
# scripts/run_daily_cerebro.bat.
#
# Usage:
#   PowerShell (Admin) -> cd C:\Users\Lluis\Documents\investment-strategy
#   powershell.exe -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1

$TaskName = "Investment_Cerebro_Daily"
$ScriptPath = "C:\Users\Lluis\Documents\investment-strategy\scripts\run_daily_cerebro.bat"

# Remove existing task if present (idempotent install).
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute $ScriptPath

$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At 8:00am

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily cerebro state regeneration for the investment dashboard." | Out-Null

Write-Host "Task '$TaskName' created (Mon-Fri 08:00)."
Write-Host "Run manually: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Inspect:     Get-ScheduledTask -TaskName '$TaskName' | Format-List *"
Write-Host "Remove:      Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"

# install_auto_commit_tasks.ps1
# Run as Administrator (one-time setup).
#
# Creates two Windows scheduled tasks that auto-commit + push the
# dashboard/data/cerebro_state.json file so Streamlit Cloud picks up
# fresh data without manual intervention. Both tasks invoke
# scripts/auto_commit_cerebro.bat which itself runs the PII safety
# regression as a hard gate before staging.
#
#   Investment_Auto_Commit_Morning    Mon-Fri 08:35  (post-cerebro daily 08:00)
#   Investment_Auto_Commit_Afternoon  Mon-Fri 15:45  (post-Claude Autonomous 15:30)
#
# Both tasks set WakeToRun=True so a sleeping laptop wakes up to push.
# Each task is capped at 15 min (PII test + git push usually ~30s).
#
# Usage (Admin PowerShell):
#   cd C:\Users\Lluis\Documents\investment-strategy
#   powershell.exe -ExecutionPolicy Bypass -File scripts\install_auto_commit_tasks.ps1
#
# Cleanup:
#   Unregister-ScheduledTask -TaskName "Investment_Auto_Commit_*" -Confirm:$false

$PROJECT = "C:\Users\Lluis\Documents\investment-strategy"
$BAT = "$PROJECT\scripts\auto_commit_cerebro.bat"

$tasks = @(
    @{
        Name        = "Investment_Auto_Commit_Morning"
        Time        = "08:35"
        Description = "Auto-commit cerebro state after the morning cerebro daily run."
    },
    @{
        Name        = "Investment_Auto_Commit_Afternoon"
        Time        = "15:45"
        Description = "Auto-commit cerebro state after the Claude Autonomous decision."
    }
)

foreach ($t in $tasks) {
    Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue

    $action  = New-ScheduledTaskAction -Execute $BAT
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
        -At $t.Time
    $settings = New-ScheduledTaskSettingsSet `
        -WakeToRun `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $t.Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $t.Description `
        -Force | Out-Null

    Write-Host "$($t.Name) created (Mon-Fri $($t.Time), WakeToRun=True)." `
        -ForegroundColor Green
}

Write-Host ""
Write-Host "Inspect:  Get-ScheduledTask -TaskName 'Investment_Auto_Commit_*' | Format-List *"
Write-Host "Run now:  Start-ScheduledTask -TaskName 'Investment_Auto_Commit_Morning'"
Write-Host "Remove:   Unregister-ScheduledTask -TaskName 'Investment_Auto_Commit_*' -Confirm:`$false"

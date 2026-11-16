# Create the scheduled task that builds the index again one time each week.
# If the task is there already, this script replaces it.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_weekly_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_weekly_task.ps1 -Day Sunday -Time 03:00
#
# To remove the task:  Unregister-ScheduledTask -TaskName "rinrikun weekly rebuild"
param(
    [string]$Day = "Monday",
    [string]$Time = "04:30",
    [string]$TaskName = "rinrikun weekly rebuild"
)

$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "weekly_rebuild.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time
# The task runs as the user who runs this script.
# S4U: the task also runs when the user is not logged on, and Windows keeps no password for it
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited
# If the computer is off at the time of the task, the task runs when the computer is on again
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description "Builds the rinrikun index again and starts its servers again." -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime | Format-List

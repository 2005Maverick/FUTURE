<#
.SYNOPSIS
  Register / list / remove FUTURE's Windows Task Scheduler jobs (DESIGN §6).

.DESCRIPTION
  Jobs live under the \FUTURE\ task folder and run as the current user while
  logged on. They are created DISABLED by default; enable them only after the
  pipeline passes gate G02 (use -Enable). One action stops everything:
  .\scripts\task_scheduler.ps1 -Disable

.EXAMPLE
  .\scripts\task_scheduler.ps1 -Register            # create all jobs, disabled
  .\scripts\task_scheduler.ps1 -Enable              # turn them on
  .\scripts\task_scheduler.ps1 -List
  .\scripts\task_scheduler.ps1 -Unregister          # remove all FUTURE jobs
#>
param(
  [switch]$Register, [switch]$Enable, [switch]$Disable, [switch]$List, [switch]$Unregister,
  [string]$Only    # optional: act on a single job name
)
$ErrorActionPreference = 'Stop'
$Root   = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Folder = '\FUTURE\'

# name -> stage, daily time (IST = local laptop time)
$Jobs = [ordered]@{
  'healthcheck' = @{ Stage = 'healthcheck'; At = '05:45' }
  'daily'       = @{ Stage = 'daily';       At = '06:00' }
  'tracks'      = @{ Stage = 'tracks';      At = '07:30' }
  # Later: labs (weekly, needs a weekly trigger here), whatsapp 13:00/19:00, inbox 21:00.
  # In local mode stages share one lock, so a stage that finds it held skips cleanly.
}

function Get-Selected { if ($Only) { $Jobs.GetEnumerator() | Where-Object Key -eq $Only } else { $Jobs.GetEnumerator() } }

if ($Register) {
  foreach ($j in Get-Selected) {
    $action  = New-ScheduledTaskAction -Execute $Python -Argument "-m future.orchestrator.run --stage $($j.Value.Stage)" -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -Daily -At $j.Value.At
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
    $task = Register-ScheduledTask -TaskPath $Folder -TaskName $j.Key -Action $action -Trigger $trigger -Settings $settings `
            -Description "FUTURE pipeline stage '$($j.Value.Stage)'" -Force
    Disable-ScheduledTask -TaskPath $Folder -TaskName $j.Key | Out-Null
    "registered (disabled): $Folder$($j.Key) daily at $($j.Value.At)"
  }
}
if ($Enable)  { foreach ($j in Get-Selected) { Enable-ScheduledTask  -TaskPath $Folder -TaskName $j.Key | Out-Null; "enabled: $($j.Key)" } }
if ($Disable) { foreach ($j in Get-Selected) { Disable-ScheduledTask -TaskPath $Folder -TaskName $j.Key | Out-Null; "disabled: $($j.Key)" } }
if ($List)    { Get-ScheduledTask -TaskPath $Folder -ErrorAction SilentlyContinue | Select-Object TaskName, State | Format-Table -AutoSize }
if ($Unregister) {
  foreach ($j in Get-Selected) {
    Unregister-ScheduledTask -TaskPath $Folder -TaskName $j.Key -Confirm:$false -ErrorAction SilentlyContinue
    "removed: $($j.Key)"
  }
}

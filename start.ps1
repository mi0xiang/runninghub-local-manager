param([ValidateSet('Web','QueueOnce','InstallQueueTask')][string]$Mode = 'Web')
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -LiteralPath (Join-Path $PSScriptRoot '.local\config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$entry = Join-Path $PSScriptRoot 'manage.py'
if ($Mode -eq 'Web') { & $cfg.python $entry web }
elseif ($Mode -eq 'QueueOnce') { & $cfg.python $entry tick }
else {
    & $cfg.python $entry status
    if ($LASTEXITCODE -ne 0) { throw 'Confirm configuration first.' }
    $confirmation = Read-Host 'Resume APPROVED jobs every two minutes. Type START'
    if ($confirmation -ne 'START') { return }
    $action = New-ScheduledTaskAction -Execute $cfg.python -Argument ('"{0}" tick' -f $entry) -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskName 'RunningHub-Local-Manager' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host 'Installed local task RunningHub-Local-Manager.'
}

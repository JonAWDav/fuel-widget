param([string]$TaskName = 'AI Fuel Widget')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
New-Item -ItemType Directory -Path (Join-Path $root 'state') -Force | Out-Null
$python = Join-Path $root '.venv\Scripts\pythonw.exe'
$script = Join-Path $root 'widget.py'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Task already exists. Inspect it before changing its settings.' }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $root 'supervise.ps1') + '"') -WorkingDirectory $root
$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$fallback = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 999
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($logon,$fallback) -Settings $settings -Principal $principal -Description 'Always-on-top Codex and Claude allowance widget. Sign-in required. Respects local intentional-stop marker.' | Out-Null
Start-ScheduledTask -TaskName $taskName
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $root 'state\installed-task.xml')
Write-Output 'Installed and started AI Fuel Widget.'

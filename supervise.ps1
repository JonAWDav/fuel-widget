param([switch]$Resume)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$paused = Join-Path $root 'state\paused'
if ($Resume -and (Test-Path -LiteralPath $paused)) { Remove-Item -LiteralPath $paused }
$guard = New-Object System.Threading.Mutex($false, 'Local\FuelSupervisorV1')
if (-not $guard.WaitOne(0)) { exit 0 }
try {
    while (-not (Test-Path -LiteralPath $paused)) {
        $process = Start-Process -FilePath (Join-Path $root '.venv\Scripts\pythonw.exe') -ArgumentList ('"' + (Join-Path $root 'widget.py') + '"') -WorkingDirectory $root -WindowStyle Hidden -PassThru
        $null = $process.Handle
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        if ((Test-Path -LiteralPath $paused) -or $exitCode -eq 0) { break }
        Add-Content -LiteralPath (Join-Path $root 'state\recovery.log') -Value ((Get-Date -Format o) + ' Widget exited unexpectedly. Restarting in 3 seconds.')
        Start-Sleep -Seconds 3
    }
} finally {
    $guard.ReleaseMutex()
    $guard.Dispose()
}

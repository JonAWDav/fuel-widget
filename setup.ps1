param([switch]$NoStartup)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js LTS, then open a new PowerShell window.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    $created = $false
    foreach ($candidate in @('py','python','python3')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command -or $command.Source -like '*WindowsApps*') { continue }
        $prefixArgs = @()
        if ($candidate -eq 'py') { $prefixArgs = @('-3') }
        try {
            & $command.Source @prefixArgs -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            & $command.Source @prefixArgs -m venv .venv
            if ($LASTEXITCODE -eq 0) { $created = $true; break }
        } catch { continue }
    }
    if (-not $created) { throw 'Install a working Python 3.11 or later and add it to PATH.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Force state | Out-Null
if ($NoStartup) {
    Write-Output 'Installed. Open Start Fuel.cmd to launch. Automatic startup was not installed.'
} else {
    & "$PSScriptRoot\install.ps1"
}

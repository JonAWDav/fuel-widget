param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [switch]$DownloadOnly,
    [switch]$NoStartup
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($env:OS -ne 'Windows_NT') { throw 'Fuel currently supports Windows only.' }

$destinationFull = [System.IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $destinationFull) {
    throw "Destination already exists: $destinationFull. Choose a new folder so existing settings are preserved."
}

$parent = Split-Path -Parent $destinationFull
if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
    throw "Parent folder does not exist: $parent"
}

if (-not $DownloadOnly) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js, then open a new PowerShell window.' }
    $pythonFound = $false
    foreach ($candidate in @('py', 'python', 'python3')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command -or $command.Source -like '*WindowsApps*') { continue }
        $prefixArgs = @()
        if ($candidate -eq 'py') { $prefixArgs = @('-3') }
        try {
            & $command.Source @prefixArgs -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $pythonFound = $true; break }
        } catch { }
    }
    if (-not $pythonFound) { throw 'Install Python 3.11 or later, then open a new PowerShell window.' }
}

$staging = Join-Path $parent ('.fuel-download-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
$archive = Join-Path $staging 'fuel-widget.zip'
$source = 'https://github.com/JonAWDav/fuel-widget/archive/refs/heads/main.zip'

try {
    Invoke-WebRequest -Uri $source -OutFile $archive -UseBasicParsing
    Expand-Archive -LiteralPath $archive -DestinationPath $staging
    $extracted = Join-Path $staging 'fuel-widget-main'
    foreach ($required in @('README.md', 'setup.ps1', 'install.ps1', 'requirements.txt', 'Start Fuel.cmd')) {
        if (-not (Test-Path -LiteralPath (Join-Path $extracted $required) -PathType Leaf)) {
            throw "Downloaded archive is missing $required. Nothing was installed."
        }
    }
    Move-Item -LiteralPath $extracted -Destination $destinationFull
    Write-Output "Downloaded Fuel to $destinationFull"
} finally {
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    if (Test-Path -LiteralPath $staging) {
        if (-not (Get-ChildItem -LiteralPath $staging -Force | Select-Object -First 1)) {
            Remove-Item -LiteralPath $staging
        }
    }
}

if ($DownloadOnly) {
    Write-Output 'Download complete. Setup and automatic startup were not run.'
    exit 0
}

$setup = Join-Path $destinationFull 'setup.ps1'
if ($NoStartup) {
    & $setup -NoStartup
} else {
    & $setup
}
if ($LASTEXITCODE -ne 0) { throw "Fuel setup failed. Files remain at $destinationFull for inspection." }
Write-Output "Fuel setup finished at $destinationFull"

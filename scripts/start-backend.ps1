<#
.SYNOPSIS
    Start the EvalPilot backend API.

.DESCRIPTION
    Creates a virtual environment if needed, installs backend requirements, and
    launches uvicorn with autoreload. The MVP needs no API key: runs are
    deterministic and offline.

.PARAMETER Host
    Bind address. Defaults to 127.0.0.1.

.PARAMETER Port
    TCP port. Defaults to 8000.

.PARAMETER NoReload
    Disable autoreload (useful for the demo recording).

.PARAMETER SkipInstall
    Skip venv creation and dependency installation.

.EXAMPLE
    ./scripts/start-backend.ps1
    ./scripts/start-backend.ps1 -Port 9000 -NoReload
#>
[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts/python.exe"

if (-not (Test-Path $backendDir)) {
    throw "backend directory not found at $backendDir"
}

if (-not $SkipInstall) {
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating virtual environment at $venvDir"
        python -m venv $venvDir
    }
    Write-Host "Installing backend requirements"
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r (Join-Path $backendDir "requirements.txt")
}

if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

$env:PYTHONPATH = $backendDir
Write-Host "Starting EvalPilot API on http://${BindHost}:${Port} (docs at /docs)"

$uvicornArgs = @(
    "-m", "uvicorn", "evalpilot.app:create_app",
    "--factory",
    "--host", $BindHost,
    "--port", $Port
)
if (-not $NoReload) {
    $uvicornArgs += @("--reload", "--reload-dir", $backendDir)
}

Push-Location $backendDir
try {
    & $venvPython @uvicornArgs
}
finally {
    Pop-Location
}

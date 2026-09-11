<#
.SYNOPSIS
    Install backend dependencies and run the pytest suite.

.DESCRIPTION
    Creates the repository virtual environment if needed, installs backend
    requirements, then runs pytest from backend/. Tests use a temporary SQLite
    database, so your backend/data directory is never touched.

.PARAMETER SkipInstall
    Skip venv creation and dependency installation.

.PARAMETER PytestArgs
    Extra arguments passed through to pytest, e.g. -PytestArgs "-k","demo".

.EXAMPLE
    ./scripts/test-backend.ps1
    ./scripts/test-backend.ps1 -PytestArgs "-v","tests/test_demo_seed.py"
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts/python.exe"

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

Push-Location $backendDir
try {
    if ($PytestArgs.Count -gt 0) {
        & $venvPython -m pytest @PytestArgs
    }
    else {
        & $venvPython -m pytest
    }
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    Write-Error "backend tests failed with exit code $exitCode"
}
exit $exitCode

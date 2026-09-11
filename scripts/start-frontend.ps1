<#
.SYNOPSIS
  Start the EvalPilot demo console.

.DESCRIPTION
  Installs frontend dependencies on first run, then starts the Vite dev server
  and opens the console in the default browser.

  If a FastAPI backend is listening on 127.0.0.1:8000 the console runs against
  it. If not, the console still runs: press "Start demo run" and it falls back
  to bundled fixtures and marks the data as offline. That fallback is deliberate
  - the demo must survive a missing backend in front of judges.

.PARAMETER Port
  Port for the Vite dev server. Default 5173.

.PARAMETER NoOpen
  Do not open a browser window.

.EXAMPLE
  .\scripts\start-frontend.ps1
  .\scripts\start-frontend.ps1 -Port 5174 -NoOpen
#>
[CmdletBinding()]
param(
    [int]$Port = 5173,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot 'frontend'

if (-not (Test-Path $frontend)) {
    throw "frontend directory not found at $frontend"
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm was not found on PATH. Install Node.js 20 or newer and try again.'
}

Push-Location $frontend
try {
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Host 'Installing frontend dependencies (first run)...' -ForegroundColor Cyan
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
    }

    $backendUp = $false
    try {
        $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' `
            -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        $backendUp = $probe.StatusCode -eq 200
    } catch {
        $backendUp = $false
    }

    Write-Host ''
    if ($backendUp) {
        Write-Host 'Backend detected at http://127.0.0.1:8000 - the console will run live.' -ForegroundColor Green
    } else {
        Write-Host 'No backend at http://127.0.0.1:8000 - the console will run on bundled fixtures.' -ForegroundColor Yellow
        Write-Host 'The offline badge in the console states this explicitly.' -ForegroundColor DarkGray
    }
    Write-Host ''

    $url = "http://127.0.0.1:$Port/"
    Write-Host "Starting Vite on $url" -ForegroundColor Cyan

    if (-not $NoOpen) {
        Start-Job -ScriptBlock {
            param($target)
            Start-Sleep -Seconds 3
            Start-Process $target
        } -ArgumentList $url | Out-Null
    }

    npm run dev -- --port $Port --strictPort
}
finally {
    Pop-Location
}

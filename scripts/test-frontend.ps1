<#
.SYNOPSIS
  Verify the EvalPilot frontend.

.DESCRIPTION
  Runs, in order:
    1. TypeScript project build  (tsc -b) - catches type and contract drift.
    2. Unit tests                (vitest run) - incl. the fixture determinism
       and comparison-integrity suites.
    3. Production build          (vite build) - proves the console ships.

  Exits non-zero on the first failure so it can gate a commit or a submission.

.PARAMETER SkipBuild
  Run only the type check and tests.

.EXAMPLE
  .\scripts\test-frontend.ps1
  .\scripts\test-frontend.ps1 -SkipBuild
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot 'frontend'

if (-not (Test-Path $frontend)) {
    throw "frontend directory not found at $frontend"
}

Push-Location $frontend
try {
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
    }

    Write-Host ''
    Write-Host '== 1/3  type check ==' -ForegroundColor Cyan
    npx tsc -b
    if ($LASTEXITCODE -ne 0) { throw "type check failed with exit code $LASTEXITCODE" }

    Write-Host ''
    Write-Host '== 2/3  unit tests ==' -ForegroundColor Cyan
    npx vitest run
    if ($LASTEXITCODE -ne 0) { throw "unit tests failed with exit code $LASTEXITCODE" }

    if (-not $SkipBuild) {
        Write-Host ''
        Write-Host '== 3/3  production build ==' -ForegroundColor Cyan
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "build failed with exit code $LASTEXITCODE" }
    }

    Write-Host ''
    Write-Host 'Frontend verified.' -ForegroundColor Green
}
finally {
    Pop-Location
}

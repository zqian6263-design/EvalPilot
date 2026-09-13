<#
.SYNOPSIS
    Export EvalPilot release-gate artifacts for CI.

.DESCRIPTION
    Downloads the gate decision, JUnit XML, SARIF JSON, Markdown report, and a
    compact Markdown pull-request summary. Exit code matches the gate:
    0 allow, 1 review, 2 block.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [string]$ApiBase = 'http://127.0.0.1:8000/api',
    [string]$OutputDirectory = '.runtime/ci-export',
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
$base = $ApiBase.TrimEnd('/')
$runId = $RunId.Trim()
$out = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $out -Force | Out-Null

Invoke-WebRequest -Uri "$base/runs/$runId/gate" -OutFile (Join-Path $out 'gate.json') -TimeoutSec $TimeoutSeconds
Invoke-WebRequest -Uri "$base/runs/$runId/junit" -OutFile (Join-Path $out 'junit.xml') -TimeoutSec $TimeoutSeconds
Invoke-WebRequest -Uri "$base/runs/$runId/sarif" -OutFile (Join-Path $out 'results.sarif') -TimeoutSec $TimeoutSeconds
Invoke-WebRequest -Uri "$base/runs/$runId/report" -OutFile (Join-Path $out 'report.json') -TimeoutSec $TimeoutSeconds

$gate = Get-Content -LiteralPath (Join-Path $out 'gate.json') -Raw | ConvertFrom-Json
$summary = @"
# EvalPilot Release Gate

- Run: ``$RunId``
- Decision: **$($gate.decision.ToUpperInvariant())**
- Exit code: ``$($gate.exit_code)``
- Baseline pass rate: ``$($gate.baseline_pass_rate)``
- Candidate pass rate: ``$($gate.candidate_pass_rate)``
- Mean difference: ``$($gate.mean_difference)``
- Reasons: ``$($gate.reasons -join ', ')``

Artifacts: ``junit.xml``, ``results.sarif``, ``report.json``.
"@
Set-Content -LiteralPath (Join-Path $out 'summary.md') -Value $summary -Encoding utf8

Write-Host "EvalPilot CI artifacts written to $out"
exit [int]$gate.exit_code

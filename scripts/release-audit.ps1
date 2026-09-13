<#
.SYNOPSIS
    Generate a self-serve release audit from a completed EvalPilot run.

.DESCRIPTION
    Downloads the gate, report, JUnit, and SARIF artifacts, then writes a
    Markdown release audit with decision evidence and explicit human sign-off
    fields. It does not require a customer interview.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [string]$ApiBase = 'http://127.0.0.1:8000/api',
    [string]$OutputDirectory = '.runtime/release-audit',
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
$base = $ApiBase.TrimEnd('/')
$out = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $out -Force | Out-Null

$gate = Invoke-RestMethod -Uri "$base/runs/$RunId/gate" -TimeoutSec $TimeoutSeconds
$report = Invoke-RestMethod -Uri "$base/runs/$RunId/report" -TimeoutSec $TimeoutSeconds
Invoke-WebRequest -Uri "$base/runs/$RunId/junit" -OutFile (Join-Path $out 'junit.xml') -TimeoutSec $TimeoutSeconds
Invoke-WebRequest -Uri "$base/runs/$RunId/sarif" -OutFile (Join-Path $out 'results.sarif') -TimeoutSec $TimeoutSeconds
Set-Content -LiteralPath (Join-Path $out 'report.json') -Value ($report | ConvertTo-Json -Depth 30) -Encoding utf8

$findings = @($report.findings)
$findingLines = if ($findings.Count -gt 0) {
    ($findings | ForEach-Object {
        "- **$($_.severity.ToUpperInvariant())** $($_.title) — $($_.description)"
    }) -join "`n"
} else {
    '- No findings recorded.'
}

$audit = @"
# Release Audit — $RunId

## Decision

- Decision: **$($gate.decision.ToUpperInvariant())**
- Exit code: **$($gate.exit_code)**
- Baseline pass rate: **$($gate.baseline_pass_rate)**
- Candidate pass rate: **$($gate.candidate_pass_rate)**
- Mean difference: **$($gate.mean_difference)**
- Confidence interval: **$($gate.ci_lower)** to **$($gate.ci_upper)**
- Reasons: **$($gate.reasons -join ', ')**

## Findings

$findingLines

## Evidence

- Report URL: $($gate.report_url)
- JUnit: ``junit.xml``
- SARIF: ``results.sarif``
- Full report: ``report.json``

## Human sign-off

| Role | Name | Decision | Notes |
|---|---|---|---|
| Release owner |  |  |  |
| Engineering owner |  |  |  |
| QA / evaluation owner |  |  |  |

## Remediation tracking

- [ ] Fix or explicitly accept each blocking finding.
- [ ] Re-run the same matched workload after the fix.
- [ ] Confirm the previous blocking scenarios now pass.
- [ ] Attach the follow-up run id and gate result.

## Reproduction

``````text
EvalPilot run: $RunId
API base: $base
Decision: $($gate.decision)
``````
"@
$auditPath = Join-Path $out 'RELEASE_AUDIT.md'
Set-Content -LiteralPath $auditPath -Value $audit -Encoding utf8
Write-Output $auditPath

<#
.SYNOPSIS
    Evaluate an EvalPilot run as a CI release gate.

.DESCRIPTION
    Reads the gate decision for a completed run and exits with the service's
    machine-readable exit code: 0 allow, 1 review, 2 block. This is the first
    integration surface for CI/CD and release automation.
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [Parameter(Mandatory = $true)]
    [string]$RunId
)

$ErrorActionPreference = 'Stop'
$uri = "http://127.0.0.1:$BackendPort/api/runs/$([uri]::EscapeDataString($RunId))/gate"
$gate = Invoke-RestMethod -Uri $uri -TimeoutSec 30
$gate | ConvertTo-Json -Depth 8
Write-Host "decision=$($gate.decision) exit_code=$($gate.exit_code)"
exit [int]$gate.exit_code

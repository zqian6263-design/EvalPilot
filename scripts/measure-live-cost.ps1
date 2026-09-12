<#
.SYNOPSIS
    Measure token usage and cost for one live EvalPilot investigation.

.DESCRIPTION
    Creates and starts an investigation for an existing run, waits for it to
    complete, reads persisted token usage from LLM-backed steps, and calculates
    peak and off-peak cost using the supplied per-million-token rates.

    Defaults are the public DeepSeek V4 Pro peak rates on 2026-09-12:
    input $1.32 / 1M tokens and output $3.96 / 1M tokens. Off-peak is half.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [int]$BackendPort = 8000,
    [int]$TimeoutSeconds = 240,
    [double]$InputPeakRate = 1.32,
    [double]$OutputPeakRate = 3.96
)

$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$BackendPort/api"
$investigation = Invoke-RestMethod -Method POST -Uri "$base/investigations" -ContentType 'application/json' -Body (@{
    run_id = $RunId
    objective = 'Measure real token usage and produce the evidence-backed release decision.'
} | ConvertTo-Json)
Invoke-RestMethod -Method Post -Uri "$base/investigations/$($investigation.id)/start" | Out-Null

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 1
    $detail = Invoke-RestMethod "$base/investigations/$($investigation.id)" -TimeoutSec 60
} while ($detail.investigation.status -notin @('completed', 'failed') -and (Get-Date) -lt $deadline)

if ($detail.investigation.status -ne 'completed') {
    throw "investigation did not complete: $($detail.investigation.status): $($detail.investigation.summary)"
}

$usageSteps = @($detail.steps | Where-Object { $_.data.usage })
$prompt = ($usageSteps | ForEach-Object { [int]$_.data.usage.prompt_tokens } | Measure-Object -Sum).Sum
$completion = ($usageSteps | ForEach-Object { [int]$_.data.usage.completion_tokens } | Measure-Object -Sum).Sum
$total = ($usageSteps | ForEach-Object { [int]$_.data.usage.total_tokens } | Measure-Object -Sum).Sum
$peak = [math]::Round(($prompt * $InputPeakRate + $completion * $OutputPeakRate) / 1000000, 6)
$offPeak = [math]::Round(($prompt * ($InputPeakRate / 2) + $completion * ($OutputPeakRate / 2)) / 1000000, 6)

[pscustomobject]@{
    run_id = $RunId
    investigation_id = $detail.investigation.id
    status = $detail.investigation.status
    decision = $detail.decision.verdict
    risk = $detail.decision.risk_level
    model = ($usageSteps | Select-Object -First 1).data.model
    usage_steps = $usageSteps.Count
    prompt_tokens = $prompt
    completion_tokens = $completion
    total_tokens = $total
    peak_cost_usd = $peak
    off_peak_cost_usd = $offPeak
} | ConvertTo-Json -Depth 6

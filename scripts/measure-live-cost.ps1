
<#
.SYNOPSIS
    Measure model, compute, storage, and total cost for one EvalPilot run.

.DESCRIPTION
    Reads persisted token usage from a live investigation when available, adds
    wall-clock run and investigation time, and computes a logical storage
    footprint from the API payloads. Rates are explicit parameters so the
    result can be recomputed with a provider's published prices.

    Defaults are reference inputs, not vendor commitments:
    - compute: $0.10 per hour of a small worker;
    - storage: $0.023 per GB-month.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [string]$InvestigationId,
    [int]$BackendPort = 8000,
    [int]$TimeoutSeconds = 240,
    [double]$InputPeakRate = 1.32,
    [double]$OutputPeakRate = 3.96,
    [double]$ComputeHourlyRate = 0.10,
    [double]$StorageGbMonthRate = 0.023,
    [int]$StorageRetentionMonths = 1
)

$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$BackendPort/api"
$run = Invoke-RestMethod "$base/runs/$RunId" -TimeoutSec 60
$runReport = Invoke-RestMethod "$base/runs/$RunId/report" -TimeoutSec 60

if (-not $InvestigationId) {
    $investigation = Invoke-RestMethod -Method POST -Uri "$base/investigations" -ContentType 'application/json' -Body (@{
        run_id = $RunId
        objective = 'Measure real token usage and produce the evidence-backed release decision.'
    } | ConvertTo-Json)
    $InvestigationId = $investigation.id
    if ($investigation.status -eq 'queued') {
        Invoke-RestMethod -Method POST -Uri "$base/investigations/$InvestigationId/start" | Out-Null
    }
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 1
    $detail = Invoke-RestMethod "$base/investigations/$InvestigationId" -TimeoutSec 60
} while ($detail.investigation.status -notin @('completed', 'failed') -and (Get-Date) -lt $deadline)

if ($detail.investigation.status -ne 'completed') {
    throw "investigation did not complete: $($detail.investigation.status): $($detail.investigation.summary)"
}

$usageSteps = @($detail.steps | Where-Object { $_.data.usage })
$investigationPrompt = ($usageSteps | ForEach-Object { [int]$_.data.usage.prompt_tokens } | Measure-Object -Sum).Sum
$investigationCompletion = ($usageSteps | ForEach-Object { [int]$_.data.usage.completion_tokens } | Measure-Object -Sum).Sum
$investigationTotal = ($usageSteps | ForEach-Object { [int]$_.data.usage.total_tokens } | Measure-Object -Sum).Sum
$judgeUsage = $runReport.metrics.judge.usage
$judgePrompt = if ($null -ne $judgeUsage -and $null -ne $judgeUsage.prompt_tokens) { [int]$judgeUsage.prompt_tokens } else { 0 }
$judgeCompletion = if ($null -ne $judgeUsage -and $null -ne $judgeUsage.completion_tokens) { [int]$judgeUsage.completion_tokens } else { 0 }
$judgeTotal = if ($null -ne $judgeUsage -and $null -ne $judgeUsage.total_tokens) { [int]$judgeUsage.total_tokens } else { 0 }
$prompt = [int]$investigationPrompt + $judgePrompt
$completion = [int]$investigationCompletion + $judgeCompletion
$total = [int]$investigationTotal + $judgeTotal

$runSeconds = ([datetimeoffset]$run.run.completed_at - [datetimeoffset]$run.run.created_at).TotalSeconds
$investigationSeconds = ([datetimeoffset]$detail.investigation.completed_at - [datetimeoffset]$detail.investigation.created_at).TotalSeconds
$computeSeconds = [math]::Max(0, $runSeconds) + [math]::Max(0, $investigationSeconds)

$runJson = $run | ConvertTo-Json -Depth 30 -Compress
$investigationJson = $detail | ConvertTo-Json -Depth 30 -Compress
$storageBytes = [Text.Encoding]::UTF8.GetByteCount($runJson) + [Text.Encoding]::UTF8.GetByteCount($investigationJson)
$storageGb = $storageBytes / 1GB

$modelPeak = ($prompt * $InputPeakRate + $completion * $OutputPeakRate) / 1000000
$modelOffPeak = ($prompt * ($InputPeakRate / 2) + $completion * ($OutputPeakRate / 2)) / 1000000
$computeCost = ($computeSeconds / 3600) * $ComputeHourlyRate
$storageCost = $storageGb * $StorageGbMonthRate * $StorageRetentionMonths

[pscustomobject]@{
    run_id = $RunId
    investigation_id = $InvestigationId
    decision = $detail.decision.verdict
    risk = $detail.decision.risk_level
    model = ($usageSteps | Select-Object -First 1).data.model
    usage_steps = $usageSteps.Count
    judge_calls = [int]$runReport.metrics.judge.calls
    judge_prompt_tokens = $judgePrompt
    judge_completion_tokens = $judgeCompletion
    judge_total_tokens = $judgeTotal
    prompt_tokens = $prompt
    completion_tokens = $completion
    total_tokens = $total
    run_seconds = [math]::Round($runSeconds, 2)
    investigation_seconds = [math]::Round($investigationSeconds, 2)
    compute_seconds = [math]::Round($computeSeconds, 2)
    logical_storage_bytes = $storageBytes
    logical_storage_mb = [math]::Round($storageBytes / 1MB, 4)
    model_peak_cost_usd = [math]::Round($modelPeak, 6)
    model_off_peak_cost_usd = [math]::Round($modelOffPeak, 6)
    compute_cost_usd = [math]::Round($computeCost, 6)
    storage_cost_usd = [math]::Round($storageCost, 8)
    total_peak_cost_usd = [math]::Round($modelPeak + $computeCost + $storageCost, 6)
    total_off_peak_cost_usd = [math]::Round($modelOffPeak + $computeCost + $storageCost, 6)
} | ConvertTo-Json -Depth 8

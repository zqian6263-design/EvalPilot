[CmdletBinding()]
param([int]$BackendPort = 8000, [int]$TimeoutSeconds = 480)

$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$BackendPort/api"
$runtime = Invoke-RestMethod -Uri "$base/runtime" -TimeoutSec 30
if ($runtime.mode -ne 'live' -or -not $runtime.llm_configured) {
    throw "runtime is not live: $($runtime | ConvertTo-Json -Compress)"
}

function Post($path, $body) {
    Invoke-RestMethod -Method POST -Uri "$base$path" -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 12) -TimeoutSec 60
}

$project = Post '/projects' @{ name = 'DeepSeek Live LLM Demo'; scenario = 'kb-qa' }
$run = Post '/runs' @{
    project_id = $project.id
    baseline_version = 'v1.0-baseline'
    candidate_version = 'v1.1-candidate'
    seed = 20260919
    case_count = 26
}
Post "/runs/$($run.id)/start" | Out-Null
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Milliseconds 500
    $runDetail = Invoke-RestMethod -Uri "$base/runs/$($run.id)" -TimeoutSec 30
} while ($runDetail.run.status -notin @('completed','failed','cancelled') -and (Get-Date) -lt $deadline)
if ($runDetail.run.status -ne 'completed') { throw "run did not complete: $($runDetail.run.status)" }

$investigation = Post '/investigations' @{
    run_id = $run.id
    objective = 'Determine whether v1.1 is safe to ship, explain the root cause, and produce an evidence-backed release decision.'
}
Post "/investigations/$($investigation.id)/start" | Out-Null
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Milliseconds 750
    $detail = Invoke-RestMethod -Uri "$base/investigations/$($investigation.id)" -TimeoutSec 60
} while ($detail.investigation.status -notin @('completed','failed') -and (Get-Date) -lt $deadline)
if ($detail.investigation.status -ne 'completed') { throw "investigation did not complete: $($detail.investigation.status)" }

$llmSteps = @($detail.steps | Where-Object { $_.data.source -eq 'llm' })
if ($llmSteps.Count -eq 0) { throw 'no LLM-generated investigation step was persisted' }
if (-not ($llmSteps | Where-Object { $_.data.model -eq $runtime.model })) { throw 'LLM steps do not name the configured model' }
$planSteps = @($llmSteps | Where-Object { $_.title -eq 'Model-guided counterfactual plan' })
if ($detail.decision.verdict -ne 'block' -or $detail.decision.risk_level -ne 'critical') { throw 'measured release decision changed in live mode' }
if (@($detail.counterfactuals).Count -lt 8) { throw 'counterfactual results are missing' }

$report = (Invoke-WebRequest -Uri "$base/investigations/$($investigation.id)/report.md" -TimeoutSec 60).Content
if ($report -notmatch 'Model release rationale') { throw 'report has no model rationale section' }

[pscustomobject]@{
    runtime_mode = $runtime.mode
    model = $runtime.model
    investigation = $detail.investigation.id
    llm_steps = $llmSteps.Count
    model_plan_steps = $planSteps.Count
    decision = $detail.decision.verdict
    risk = $detail.decision.risk_level
    counterfactuals = @($detail.counterfactuals).Count
    report_has_model_rationale = $true
} | Format-List

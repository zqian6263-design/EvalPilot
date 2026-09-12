[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$TimeoutSeconds = 480
)

$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$BackendPort/api"
$failures = [System.Collections.Generic.List[string]]::new()

function Step([string]$name, [bool]$ok, [string]$detail = '') {
    $mark = if ($ok) { 'PASS' } else { 'FAIL' }
    $suffix = if ($detail) { " — $detail" } else { '' }
    Write-Host "  $mark  $name$suffix"
    if (-not $ok) { $failures.Add($name) }
}

function Api([string]$method, [string]$path, $body = $null) {
    $params = @{ Method = $method; Uri = "$base$path"; TimeoutSec = 30 }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ($body | ConvertTo-Json -Depth 12)
    }
    Invoke-RestMethod @params
}

try {
    & (Join-Path $PSScriptRoot 'start-all.ps1') -BackendPort $BackendPort -FrontendPort $FrontendPort -TimeoutSeconds $TimeoutSeconds -SkipInstall

    Write-Host "`n-- V2 health"
    $health = Api GET '/health'
    Step 'the backend health endpoint answers' ($health.status -eq 'ok')

    Write-Host "`n-- Build a completed run"
    $projects = Api GET '/projects'
    $project = $projects | Where-Object { $_.name -eq 'Enterprise Knowledge Base QA' } | Select-Object -First 1
    if (-not $project) {
        $project = Api POST '/projects' @{ name = 'Enterprise Knowledge Base QA'; scenario = 'kb-qa' }
    }
    $run = Api POST '/runs' @{
        project_id = $project.id
        baseline_version = 'v1.0-baseline'
        candidate_version = 'v1.1-candidate'
        seed = 20260919
        case_count = 26
    }
    Api POST "/runs/$($run.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 500
        $detail = Api GET "/runs/$($run.id)"
        $status = $detail.run.status
    } while ($status -notin @('completed','failed','cancelled') -and (Get-Date) -lt $deadline)
    Step 'the regression run completes' ($status -eq 'completed') $status
    Step 'the confirmed 26-case run has eight regressions' ($detail.run.case_count -eq 26 -and $detail.finding_count -eq 8) "cases=$($detail.run.case_count) findings=$($detail.finding_count)"

    Write-Host "`n-- Autonomous investigation"
    $objective = 'Determine whether v1.1 is safe to ship, identify the root cause, and produce an evidence-backed release decision.'
    $investigation = Api POST '/investigations' @{ run_id = $run.id; objective = $objective }
    if ($investigation.status -eq 'queued') {
        Api POST "/investigations/$($investigation.id)/start" | Out-Null
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 500
        $investigationDetail = Api GET "/investigations/$($investigation.id)"
        $invStatus = $investigationDetail.investigation.status
    } while ($invStatus -notin @('completed','failed') -and (Get-Date) -lt $deadline)
    Step 'the investigation completes' ($invStatus -eq 'completed') $invStatus

    $steps = @($investigationDetail.steps)
    foreach ($kind in @('risk','memory','probe','counterfactual','decision')) {
        Step "the investigation contains a $kind step" (($steps.kind -contains $kind))
    }
    Step 'at least three risk hypotheses are present' ((@($steps | Where-Object kind -eq 'risk')).Count -ge 3)
    Step 'at least two historical incidents are recalled' ((@($investigationDetail.memory_matches)).Count -ge 2)

    $counterfactuals = @($investigationDetail.counterfactuals)
    Step 'every regressed scenario has a replay' ((@($counterfactuals | Select-Object -ExpandProperty scenario_id -Unique)).Count -ge 8)
    Step 'the compression intervention is the dominant root cause' ((@($counterfactuals | Where-Object { $_.intervention -eq 'compression_disabled' -and $_.verdict -eq 'root_cause' })).Count -ge 7)
    Step 'the credential disclosure is attributed to the security guard' ((@($counterfactuals | Where-Object { $_.scenario_id -eq 'prompt-injection-password' -and $_.intervention -eq 'security_guard_enabled' -and $_.verdict -eq 'root_cause' })).Count -eq 1)
    Step 'the measured replay has evidence for every experiment' (@($counterfactuals | Where-Object { -not $_.evidence_ids }).Count -eq 0)

    $decision = $investigationDetail.decision
    Step 'the release decision blocks the candidate' ($decision.verdict -eq 'block') $decision.verdict
    Step 'the release risk is critical' ($decision.risk_level -eq 'critical') $decision.risk_level
    Step 'the decision cites persisted findings' (@($decision.blocking_findings).Count -gt 0)

    $report = (Invoke-WebRequest -Uri "$base/investigations/$($investigation.id)/report.md" -TimeoutSec 30).Content
    Step 'the Markdown report states the block decision' ($report -match 'BLOCK|block')
    Step 'the Markdown report includes an evidence index' ($report -match 'Evidence' -or $report -match 'evidence')
    Step 'the frontend serves the investigation workspace shell' ((Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSec 10).StatusCode -eq 200)

    if ($failures.Count -gt 0) {
        throw "V2 E2E failed: $($failures -join '; ')"
    }
    Write-Host "`nV2 E2E OK" -ForegroundColor Green
} finally {
    & (Join-Path $PSScriptRoot 'start-all.ps1') -BackendPort $BackendPort -FrontendPort $FrontendPort -Stop | Out-Host
}

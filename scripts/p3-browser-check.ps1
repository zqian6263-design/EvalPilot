[CmdletBinding()]
param(
    [int]$BackendPort = 8150,
    [int]$SutPort = 8120,
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$integrationDir = Join-Path $repoRoot 'integrations/mem0_retro'
$workloadFile = Join-Path $integrationDir 'browser_workload.json'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPython)) { $venvPython = 'python' }
$runtimeRoot = Join-Path $repoRoot '.runtime'
$runToken = [guid]::NewGuid().ToString('N')
$workDir = Join-Path $runtimeRoot "p3-browser-$runToken"
$null = New-Item -ItemType Directory -Path $workDir -Force
$api = "http://127.0.0.1:$BackendPort/api"
$sutUrl = "http://127.0.0.1:$SutPort"
$failures = [System.Collections.Generic.List[string]]::new()
$sutJob = $null
$backendJob = $null

function Step([string]$name, [bool]$ok, [string]$detail = '') {
    $mark = if ($ok) { 'PASS' } else { 'FAIL' }
    $suffix = if ($detail) { " - $detail" } else { '' }
    Write-Host "  $mark  $name$suffix"
    if (-not $ok) { $failures.Add($name) }
}

function Wait-Http([string]$url, [int]$seconds = 60) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    return $false
}

function Api([string]$method, [string]$path, $body = $null) {
    $params = @{ Method = $method; Uri = "$api$path"; TimeoutSec = 60 }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ($body | ConvertTo-Json -Depth 12)
    }
    Invoke-RestMethod @params
}

try {
    Write-Host '-- Prepare browser SUT dependencies'
    if (-not (Test-Path (Join-Path $integrationDir 'node_modules'))) {
        & npm ci --prefix $integrationDir
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    }

    Write-Host '-- Start the public mem0 HTTP SUT with browser UI'
    $sutJob = Start-Job -ScriptBlock {
        param($dir, $serverPort)
        Set-Location $dir
        $env:MEM0_RETRO_PORT = "$serverPort"
        node server.mjs
    } -ArgumentList $integrationDir, $SutPort
    $sutHealthy = Wait-Http "$sutUrl/health" 60
    Step 'browser SUT is healthy' $sutHealthy
    if (-not $sutHealthy) { throw 'browser SUT did not become healthy' }
    $ui = Invoke-WebRequest "$sutUrl/?version=mem0ai-3.1.1" -UseBasicParsing
    Step 'browser SUT serves a real interaction surface' ($ui.Content -match 'Memory scope browser check')

    Write-Host '-- Start EvalPilot with browser execution enabled'
    $browserExe = @('C:\Program Files\Google\Chrome\Application\chrome.exe','C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $browserExe) { throw 'Chrome or Edge is required for the browser acceptance check' }
    $backendJob = Start-Job -ScriptBlock {
        param($root, $python, $backendPort, $serverUrl, $workload, $work, $executable)
        Set-Location $root
        $env:PYTHONPATH = (Join-Path $root 'backend')
        $env:EVALPILOT_DB_PATH = (Join-Path $work 'evalpilot.db')
        $env:EVALPILOT_BROWSER_ENABLED = 'true'
        $env:EVALPILOT_BROWSER_TARGET_URL = $serverUrl
        $env:EVALPILOT_BROWSER_ALLOWED_HOSTS = ([uri]$serverUrl).Host
        $env:EVALPILOT_BROWSER_EXECUTABLE = $executable
        $env:EVALPILOT_BROWSER_TIMEOUT_SECONDS = '30'
        $env:EVALPILOT_WORKLOAD_FILE = $workload
        $env:EVALPILOT_STEP_DELAY = '0'
        & $python -m uvicorn evalpilot.app:create_app --factory --host 127.0.0.1 --port $backendPort --log-level warning
    } -ArgumentList $repoRoot, $venvPython, $BackendPort, $sutUrl, $workloadFile, $workDir, $browserExe
    Step 'EvalPilot backend is healthy' (Wait-Http "$api/health" 60)
    $runtime = Api GET '/runtime'
    Step 'browser_run is advertised by the runtime' ($runtime.tools -contains 'browser_run')

    $project = Api POST '/projects' @{ name = 'Browser mem0 retrospective'; scenario = 'mem0-browser' }
    $run = Api POST '/runs' @{
        project_id = $project.id
        baseline_version = 'mem0ai-3.1.1'
        candidate_version = 'mem0ai-3.1.0'
        seed = 20260919
        case_count = 6
    }
    Api POST "/runs/$($run.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $detail = Api GET "/runs/$($run.id)"
    } while ($detail.run.status -notin @('completed', 'failed', 'cancelled') -and (Get-Date) -lt $deadline)

    $report = Api GET "/runs/$($run.id)/report"
    $screenshots = @($detail.evidence | Where-Object { $_.kind -eq 'screenshot' })
    $traces = @($detail.evidence | Where-Object { $_.kind -eq 'trace' })
    $regressed = @($report.metrics.regressed_scenarios)
    Step 'browser run completes' ($detail.run.status -eq 'completed')
    Step 'browser run detects all three regressions' ($regressed.Count -eq 3) ($regressed -join ',')
    Step 'three browser controls remain stable' (@($report.metrics.control_scenarios).Count -eq 3)
    Step 'every browser case has screenshot evidence' ($screenshots.Count -eq 12) "screenshots=$($screenshots.Count)"
    Step 'screenshot paths are unique' (@($screenshots.uri | Sort-Object -Unique).Count -eq $screenshots.Count)
    Step 'every browser case has trace evidence' ($traces.Count -eq 12) "traces=$($traces.Count)"

    $investigation = Api POST '/investigations' @{
        run_id = $run.id
        objective = 'Diagnose the browser-observed tenant isolation regression and verify recovery through the browser.'
    }
    Api POST "/investigations/$($investigation.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $investigationDetail = Api GET "/investigations/$($investigation.id)"
    } while ($investigationDetail.investigation.status -notin @('completed', 'failed') -and (Get-Date) -lt $deadline)

    $counterfactuals = @($investigationDetail.counterfactuals)
    Step 'browser investigation completes' ($investigationDetail.investigation.status -eq 'completed')
    Step 'browser counterfactual count matches regressions' ($counterfactuals.Count -eq 3) "replays=$($counterfactuals.Count)"
    Step 'browser replays confirm root cause' (@($counterfactuals | Where-Object { $_.verdict -ne 'root_cause' }).Count -eq 0)
    Step 'release remains blocked at critical risk' ($investigationDetail.decision.verdict -eq 'block' -and $investigationDetail.decision.risk_level -eq 'critical')

    # A verdict the deterministic fallback produced is a prediction. The engine
    # says "Replayed ..."; the fallback says "is predicted to restore ...".
    Step 'every browser replay is a measurement, not a prediction' (
        @($counterfactuals | Where-Object { -not $_.rationale.StartsWith('Replayed ') -or $_.rationale -match 'predicted' }).Count -eq 0
    )

    # ... and the evidence must show it: each counterfactual replays two arms
    # through the browser, so the run gains one screenshot and one trace per arm,
    # and the replay trace records the intervention that produced it.
    $afterInvestigation = Api GET "/runs/$($run.id)"
    $allScreenshots = @($afterInvestigation.evidence | Where-Object { $_.kind -eq 'screenshot' })
    # Only the browser executor records a request on its trace row; the
    # investigation's own follow-up probes write trace rows without one.
    $browserTraces = @(
        $afterInvestigation.evidence | Where-Object { $_.kind -eq 'trace' -and $_.payload.request }
    )
    $replayTraces = @(
        $browserTraces | Where-Object { $_.payload.request.intervention -eq 'identity_metadata_stripped' }
    )
    $expectedReplayArms = $counterfactuals.Count * 2
    Step 'every counterfactual replayed both arms through the browser' (
        $replayTraces.Count -eq $counterfactuals.Count
    ) "intervention_traces=$($replayTraces.Count) replays=$($counterfactuals.Count)"
    Step 'every browser replay persisted its own browser trace' (
        $browserTraces.Count -eq (12 + $expectedReplayArms)
    ) "browser_traces=$($browserTraces.Count) expected=$(12 + $expectedReplayArms)"
    Step 'every browser replay persisted its own screenshot' (
        $allScreenshots.Count -eq (12 + $expectedReplayArms)
    ) "screenshots=$($allScreenshots.Count)"
    Step 'every replayed arm really loaded the page' (
        @($replayTraces | Where-Object { @($_.payload.actions).Count -eq 0 }).Count -eq 0
    )

    if ($failures.Count -gt 0) { throw "P3 browser acceptance failed: $($failures -join '; ')" }

    $summary = [ordered]@{
        status = 'passed'
        run_id = $run.id
        investigation_id = $investigation.id
        matched_scenarios = $report.metrics.scenario_count
        regressed_scenarios = $regressed
        control_scenarios = @($report.metrics.control_scenarios)
        screenshot_evidence = $screenshots.Count
        trace_evidence = $traces.Count
        measured_browser_replays = $replayTraces.Count
        measured_replay_arms = $expectedReplayArms
        measured_replay_screenshots = $allScreenshots.Count
        measured_replay_traces = $browserTraces.Count
        mean_difference = $report.metrics.mean_difference
        ci = @($report.metrics.ci_lower, $report.metrics.ci_upper)
        counterfactuals = @($counterfactuals | ForEach-Object { [ordered]@{ scenario_id = $_.scenario_id; intervention = $_.intervention; verdict = $_.verdict; original_score = $_.original_score; counterfactual_score = $_.counterfactual_score; rationale = $_.rationale } })
        decision = $investigationDetail.decision.verdict
        risk_level = $investigationDetail.decision.risk_level
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $workDir 'summary.json') -Encoding utf8
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $repoRoot 'docs/P3_BROWSER_RESULT.json') -Encoding utf8
    Write-Host "`nP3 browser acceptance OK" -ForegroundColor Green
    Write-Host "Evidence: $(Join-Path $repoRoot 'docs/P3_BROWSER_RESULT.json')"
} catch {
    Write-Host "`nP3 browser acceptance FAILED: $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    if ($backendJob) { Stop-Job $backendJob -ErrorAction SilentlyContinue; Remove-Job $backendJob -Force -ErrorAction SilentlyContinue }
    if ($sutJob) { Stop-Job $sutJob -ErrorAction SilentlyContinue; Remove-Job $sutJob -Force -ErrorAction SilentlyContinue }
}

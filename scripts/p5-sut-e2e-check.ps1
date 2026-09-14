<#
.SYNOPSIS
    Prove the P5 onboarding template survives a real EvalPilot evaluation.

.DESCRIPTION
    Boundary #2 of the P5 report: the onboarding template had only been validated
    at the contract level (scripts/validate-sut.ps1), never by an actual
    EvalPilot run. This script closes that gap with live processes and live API
    results:

      1. Starts integrations/sut_template as a real HTTP SUT process.
      2. Requires scripts/validate-sut.ps1 to accept it.
      3. Starts EvalPilot with EVALPILOT_SUT_URL / EVALPILOT_WORKLOAD_FILE
         pointed at the template (no core evaluation logic is changed).
      4. Runs a same-version control (candidate vs candidate): no regression.
      5. Runs baseline vs candidate: the five declared regression scenarios
         regress, the three controls stay intact, and the paired interval clears
         the threshold.
      6. Runs the investigation: every regressed scenario is replayed through the
         HTTP boundary with the template's own intervention (a name that is not in
         the evaluator's built-in vocabulary), and every replay is confirmed as a
         measured root cause rather than a fallback prediction.
      7. Writes docs/P5_E2E_RESULT.json with the measured facts.

    Only the processes this script starts are stopped at the end.

.PARAMETER SutPort
    Port for the template SUT. Default 8030.

.PARAMETER BackendPort
    Port for the EvalPilot backend. Default 8031.

.PARAMETER TimeoutSeconds
    Per-run and per-investigation deadline in seconds. Default 300.

.PARAMETER ResultPath
    Where the committed evidence file is written. Default docs/P5_E2E_RESULT.json.
#>
[CmdletBinding()]
param(
    [int]$SutPort = 8030,
    [int]$BackendPort = 8031,
    [int]$TimeoutSeconds = 300,
    [string]$ResultPath = 'docs/P5_E2E_RESULT.json'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$templateDir = Join-Path $repoRoot 'integrations/sut_template'
$workloadFile = Join-Path $templateDir 'workload.json'
$validateScript = Join-Path $repoRoot 'scripts/validate-sut.ps1'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPython)) { $venvPython = 'python' }

$runToken = [guid]::NewGuid().ToString('N')
$workDir = Join-Path $repoRoot ".runtime/p5-sut-e2e-$runToken"
$null = New-Item -ItemType Directory -Path $workDir -Force
$cacheDir = Join-Path $workDir 'cache'
$null = New-Item -ItemType Directory -Path $cacheDir -Force

$sutUrl = "http://127.0.0.1:$SutPort"
$api = "http://127.0.0.1:$BackendPort/api"
$failures = [System.Collections.Generic.List[string]]::new()
$processes = [System.Collections.Generic.List[object]]::new()
$sutProcess = $null
$backendProcess = $null

# Scenarios the template workload declares as deliberate candidate regressions,
# and the ones it declares as matched controls.
$expectedRegressed = @(
    'credential-handling-policy',
    'escalation-deadline',
    'escalation-human-handoff',
    'refund-processing-time',
    'shipping-express-cutoff'
)
$expectedControls = @(
    'refund-payout-method',
    'refund-return-window',
    'shipping-standard-sla'
)

# The template's own intervention name. It is deliberately *not* a member of the
# evaluator's built-in Intervention vocabulary, so this run proves that a custom
# intervention an external SUT declares is executed and measured rather than
# silently answered by the deterministic fallback.
$customIntervention = 'full_context_restored'
$builtinInterventions = @(
    'compression_disabled',
    'security_guard_enabled',
    'retrieval_top_k_restored',
    'unicode_normalization_restored',
    'memory_scope_restored',
    'cache_bypass_enabled',
    'identity_metadata_stripped',
    'none'
)

function Step([string]$name, [bool]$ok, [string]$detail = '') {
    $mark = if ($ok) { 'PASS' } else { 'FAIL' }
    $suffix = if ($detail) { " - $detail" } else { '' }
    Write-Host "  $mark  $name$suffix"
    if (-not $ok) { $failures.Add($name) }
}

function Assert-PortFree([int]$port) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw "port $port is already in use" }
}

function Wait-Http([string]$url, [int]$seconds = 45) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    return $false
}

function Start-ProcessChecked(
    [string]$name,
    [string[]]$arguments,
    [string]$workingDirectory,
    [string]$stdoutLog,
    [string]$stderrLog
) {
    $process = Start-Process -FilePath $venvPython -ArgumentList $arguments `
        -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    $processes.Add($process)
    return @{ name = $name; process = $process; stdout = $stdoutLog; stderr = $stderrLog }
}

function Stop-Tree($process) {
    if ($null -eq $process) { return }
    if (-not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
    }
}

function Server-Tail([string]$stdoutLog, [string]$stderrLog) {
    $parts = @()
    if (Test-Path $stdoutLog) { $parts += Get-Content -LiteralPath $stdoutLog -Tail 20 -ErrorAction SilentlyContinue }
    if (Test-Path $stderrLog) { $parts += Get-Content -LiteralPath $stderrLog -Tail 20 -ErrorAction SilentlyContinue }
    return ($parts -join "`n")
}

function Api([string]$method, [string]$path, $body = $null) {
    $params = @{ Method = $method; Uri = "$api$path"; TimeoutSec = 60 }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ($body | ConvertTo-Json -Depth 12)
    }
    Invoke-RestMethod @params
}

function New-Run([string]$projectId, [string]$baseline, [string]$candidate, [int]$caseCount = 8) {
    Api POST '/runs' @{
        project_id = $projectId
        baseline_version = $baseline
        candidate_version = $candidate
        seed = 20260919
        case_count = $caseCount
    }
}

function Start-And-WaitRun($run) {
    Api POST "/runs/$($run.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $detail = $null
    do {
        Start-Sleep -Milliseconds 250
        $detail = Api GET "/runs/$($run.id)"
        $status = $detail.run.status
    } while ($status -notin @('completed', 'failed', 'cancelled') -and (Get-Date) -lt $deadline)
    return $detail
}

function Trace-Requests($detail) {
    return @(
        $detail.evidence |
            Where-Object { $_.kind -eq 'trace' -and $_.payload.request } |
            ForEach-Object { $_.payload.request }
    )
}

try {
    Assert-PortFree $SutPort
    Assert-PortFree $BackendPort

    Write-Host "`n-- Start the onboarding template as a real SUT"
    $sutProcess = Start-ProcessChecked `
        -name 'template-sut' `
        -arguments @(
            '-m', 'uvicorn', 'app:app',
            '--app-dir', 'integrations/sut_template',
            '--host', '127.0.0.1', '--port', "$SutPort", '--log-level', 'warning'
        ) `
        -workingDirectory $repoRoot `
        -stdoutLog (Join-Path $workDir 'sut.out.log') `
        -stderrLog (Join-Path $workDir 'sut.err.log')
    $sutHealthy = Wait-Http "$sutUrl/health" 45
    if (-not $sutHealthy) {
        throw "template SUT did not become healthy:`n$(Server-Tail $sutProcess.stdout $sutProcess.stderr)"
    }
    $health = Invoke-RestMethod -Uri "$sutUrl/health" -TimeoutSec 10
    $capabilities = Invoke-RestMethod -Uri "$sutUrl/capabilities" -TimeoutSec 10
    Step 'the template SUT is healthy' ($health.status -eq 'ok') "service=$($health.service)"
    Step 'the template SUT advertises both revisions and both interventions' (
        ($capabilities.versions -contains 'v1.0-baseline') -and
        ($capabilities.versions -contains 'v1.1-candidate') -and
        ($capabilities.interventions -contains 'compression_disabled') -and
        ($capabilities.interventions -contains $customIntervention)
    ) "versions=$($capabilities.versions -join ',') interventions=$($capabilities.interventions -join ',')"

    Write-Host "`n-- Onboarding gate: scripts/validate-sut.ps1"
    $validateReport = Join-Path $workDir 'validate-sut.json'
    $validateOutput = & pwsh -NoProfile -File $validateScript `
        -BaseUrl $sutUrl -Workload $workloadFile -TimeoutSeconds 30 -JsonReport $validateReport 2>&1
    $validateExit = $LASTEXITCODE
    [System.IO.File]::WriteAllText(
        (Join-Path $workDir 'validate-sut.log'),
        ($validateOutput -join [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false)
    )
    $validateSummary = if (Test-Path $validateReport) {
        Get-Content -Raw -LiteralPath $validateReport | ConvertFrom-Json
    } else { $null }
    Step 'validate-sut.ps1 accepts the template SUT' ($validateExit -eq 0) "exit=$validateExit"
    Step 'the onboarding report has no failed check' (
        $null -ne $validateSummary -and $validateSummary.checks_failed -eq 0
    ) "checks=$($validateSummary.checks_total)"

    Write-Host "`n-- Start EvalPilot against the template SUT"
    $env:PYTHONPATH = $backendDir
    $env:EVALPILOT_DB_PATH = Join-Path $workDir 'evalpilot.db'
    $env:EVALPILOT_ARTIFACTS_DIR = Join-Path $workDir 'artifacts'
    $env:EVALPILOT_STEP_DELAY = '0'
    $env:EVALPILOT_SUT_URL = $sutUrl
    $env:EVALPILOT_SUT_DISCOVERY = 'true'
    $env:EVALPILOT_SUT_OFFLINE = 'false'
    $env:EVALPILOT_SUT_CACHE_DIR = $cacheDir
    $env:EVALPILOT_WORKLOAD_FILE = $workloadFile
    $backendProcess = Start-ProcessChecked `
        -name 'evalpilot-backend' `
        -arguments @(
            '-m', 'uvicorn', 'evalpilot.app:create_app', '--factory',
            '--host', '127.0.0.1', '--port', "$BackendPort", '--log-level', 'warning'
        ) `
        -workingDirectory $backendDir `
        -stdoutLog (Join-Path $workDir 'backend.out.log') `
        -stderrLog (Join-Path $workDir 'backend.err.log')
    if (-not (Wait-Http "$api/health" 60)) {
        throw "EvalPilot backend did not become healthy:`n$(Server-Tail $backendProcess.stdout $backendProcess.stderr)"
    }
    Step 'EvalPilot backend is healthy' $true

    $project = Api POST '/projects' @{
        name = "P5 onboarding template $runToken"
        scenario = 'kb-qa'
    }

    Write-Host "`n-- Same-version control: candidate vs candidate"
    $controlRun = New-Run $project.id 'v1.1-candidate' 'v1.1-candidate'
    $controlDetail = Start-And-WaitRun $controlRun
    $controlReport = Api GET "/runs/$($controlRun.id)/report"
    Step 'the same-version control completes' ($controlDetail.run.status -eq 'completed') $controlDetail.run.status
    Step 'the same-version control reports no regression' (
        $controlReport.metrics.regression_detected -eq $false -and
        @($controlReport.metrics.regressed_scenarios).Count -eq 0
    ) "mean=$($controlReport.metrics.mean_difference)"
    Step 'the same-version control has a zero mean difference' (
        [double]$controlReport.metrics.mean_difference -eq 0.0
    ) "mean=$($controlReport.metrics.mean_difference)"

    Write-Host "`n-- Evaluation: v1.0-baseline vs v1.1-candidate"
    $regressionRun = New-Run $project.id 'v1.0-baseline' 'v1.1-candidate'
    $regressionDetail = Start-And-WaitRun $regressionRun
    $regressionReport = Api GET "/runs/$($regressionRun.id)/report"
    $metrics = $regressionReport.metrics
    $regressed = @($metrics.regressed_scenarios)
    $controls = @($metrics.control_scenarios)

    Step 'the evaluation run completes' ($regressionDetail.run.status -eq 'completed') $regressionDetail.run.status
    Step 'all eight template scenarios are matched' ($metrics.matched_scenarios -eq 8) "matched=$($metrics.matched_scenarios)"
    Step 'the baseline answers every scenario correctly' (
        [double]$metrics.baseline_pass_rate -eq 1.0 -and [double]$metrics.baseline_score -eq 1.0
    ) "pass_rate=$($metrics.baseline_pass_rate) score=$($metrics.baseline_score)"
    Step 'the candidate scores exactly the three intact controls' (
        [double]$metrics.candidate_score -eq 0.6875
    ) "candidate_score=$($metrics.candidate_score) candidate_pass_rate=$($metrics.candidate_pass_rate)"
    Step 'a real regression is detected' ($metrics.regression_detected -eq $true)
    Step 'exactly the five declared regression scenarios regress' (
        ($regressed.Count -eq $expectedRegressed.Count) -and
        (@(Compare-Object -ReferenceObject $expectedRegressed -DifferenceObject $regressed).Count -eq 0)
    ) "regressed=$($regressed -join ',')"
    Step 'the three declared controls stay intact' (
        ($controls.Count -eq $expectedControls.Count) -and
        (@(Compare-Object -ReferenceObject $expectedControls -DifferenceObject $controls).Count -eq 0)
    ) "controls=$($controls -join ',')"
    Step 'the paired interval clears the regression threshold' (
        [double]$metrics.ci_upper -lt (0 - [double]$metrics.regression_threshold)
    ) "CI=[$($metrics.ci_lower), $($metrics.ci_upper)] threshold=-$($metrics.regression_threshold)"
    Step 'the mean difference is the measured drop' (
        [math]::Abs([double]$metrics.mean_difference - (-0.3125)) -lt 0.000001
    ) "mean=$($metrics.mean_difference)"
    Step 'the run persists an evidence-linked finding per regressed scenario' (
        $regressionDetail.finding_count -ge 5
    ) "findings=$($regressionDetail.finding_count)"

    $requests = Trace-Requests $regressionDetail
    $requestVersions = @($requests | ForEach-Object { [string]$_.version } | Sort-Object -Unique)
    Step 'every case was executed against the template over HTTP' ($requests.Count -eq 16) "traces=$($requests.Count)"
    Step 'run evidence carries both real template revisions' (
        ($requestVersions -contains 'v1.0-baseline') -and ($requestVersions -contains 'v1.1-candidate')
    ) "versions=$($requestVersions -join ',')"

    Write-Host "`n-- Investigation and counterfactual replay through the HTTP boundary"
    $investigation = Api POST '/investigations' @{
        run_id = $regressionRun.id
        objective = 'Determine whether the compressed candidate revision is safe to ship and confirm the root cause of every regressed knowledge-base scenario.'
    }
    if ($investigation.status -eq 'queued') {
        Api POST "/investigations/$($investigation.id)/start" | Out-Null
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 400
        $investigationDetail = Api GET "/investigations/$($investigation.id)"
        $investigationStatus = $investigationDetail.investigation.status
    } while ($investigationStatus -notin @('completed', 'failed') -and (Get-Date) -lt $deadline)

    $counterfactuals = @($investigationDetail.counterfactuals)
    Step 'the investigation completes' ($investigationStatus -eq 'completed') $investigationStatus
    Step 'every regressed scenario is replayed' ($counterfactuals.Count -eq 5) "replays=$($counterfactuals.Count)"
    Step 'every replay uses the intervention the template advertises' (
        @($counterfactuals | Where-Object { $_.intervention -ne $customIntervention }).Count -eq 0
    ) "interventions=$(@($counterfactuals | ForEach-Object { $_.intervention } | Sort-Object -Unique) -join ',')"
    Step 'every replay confirms the root cause' (
        @($counterfactuals | Where-Object { $_.verdict -ne 'root_cause' }).Count -eq 0
    ) "verdicts=$(@($counterfactuals | ForEach-Object { $_.verdict } | Sort-Object -Unique) -join ',')"
    Step 'every replay recovers the lost score' (
        @($counterfactuals | Where-Object { [double]$_.counterfactual_score -le [double]$_.original_score }).Count -eq 0
    ) "original=$(@($counterfactuals | ForEach-Object { $_.original_score } | Sort-Object -Unique) -join ',') recovered=$(@($counterfactuals | ForEach-Object { $_.counterfactual_score } | Sort-Object -Unique) -join ',')"
    Step 'every replay is a measured full recovery, not a fallback prediction' (
        @($counterfactuals | Where-Object { [double]$_.counterfactual_score -ne 1.0 }).Count -eq 0
    ) "recovered=$(@($counterfactuals | ForEach-Object { $_.counterfactual_score } | Sort-Object -Unique) -join ',')"
    Step 'every replay is evidence-linked' (
        @($counterfactuals | Where-Object { @($_.evidence_ids).Count -eq 0 }).Count -eq 0
    )
    Step 'the release decision blocks the candidate' ($investigationDetail.decision.verdict -eq 'block') `
        "verdict=$($investigationDetail.decision.verdict) risk=$($investigationDetail.decision.risk_level)"

    $afterInvestigation = Api GET "/runs/$($regressionRun.id)"
    $replayRequests = @(
        (Trace-Requests $afterInvestigation) | Where-Object { $_.intervention }
    )
    Step 'every replay really crossed the HTTP boundary' ($replayRequests.Count -eq 5) "measured_replays=$($replayRequests.Count)"
    Step 'every replay requested the custom intervention' (
        @($replayRequests | Where-Object { $_.intervention -ne $customIntervention }).Count -eq 0
    )
    Step 'the custom intervention name is not part of the built-in vocabulary' (
        $builtinInterventions -notcontains $customIntervention
    ) "builtin=$($builtinInterventions -join ',')"

    $reportMarkdown = (Invoke-WebRequest -Uri "$api/investigations/$($investigation.id)/report.md" -TimeoutSec 60 -UseBasicParsing).Content
    $reportPath = Join-Path $workDir 'investigation-report.md'
    [System.IO.File]::WriteAllText($reportPath, $reportMarkdown, [System.Text.UTF8Encoding]::new($false))
    Step 'the investigation report is downloadable' (
        (Test-Path $reportPath) -and ((Get-Item $reportPath).Length -gt 0)
    ) "bytes=$((Get-Item $reportPath).Length)"

    if ($failures.Count -gt 0) { throw "P5 external-SUT evaluation failed: $($failures -join '; ')" }

    $evidenceDir = ".runtime/p5-sut-e2e-$runToken"
    $result = [ordered]@{
        status = 'passed'
        workload = 'sut-template-sample'
        workload_file = 'integrations/sut_template/workload.json'
        sut = 'integrations/sut_template (FastAPI onboarding template)'
        sut_url = $sutUrl
        sut_interventions = @($capabilities.interventions)
        custom_intervention = $customIntervention
        onboarding_gate = [ordered]@{
            command = "pwsh -NoProfile -File ./scripts/validate-sut.ps1 -BaseUrl $sutUrl -Workload ./integrations/sut_template/workload.json"
            exit_code = $validateExit
            checks_total = $validateSummary.checks_total
            checks_failed = $validateSummary.checks_failed
        }
        control_run_id = $controlRun.id
        regression_run_id = $regressionRun.id
        investigation_id = $investigation.id
        cases_per_version = 8
        matched_scenarios = $metrics.matched_scenarios
        baseline_version = $metrics.baseline_version
        candidate_version = $metrics.candidate_version
        baseline_pass_rate = $metrics.baseline_pass_rate
        candidate_pass_rate = $metrics.candidate_pass_rate
        baseline_score = $metrics.baseline_score
        candidate_score = $metrics.candidate_score
        mean_difference = $metrics.mean_difference
        ci = @($metrics.ci_lower, $metrics.ci_upper)
        regression_threshold = $metrics.regression_threshold
        direction = $metrics.direction
        regression_confirmed = $metrics.regression_confirmed
        regressed_scenarios = $regressed
        control_scenarios = $controls
        failing_scenarios = @($metrics.failing_scenarios)
        findings = $regressionDetail.finding_count
        http_trace_evidence = $requests.Count
        control_run_mean_difference = $controlReport.metrics.mean_difference
        decision = $investigationDetail.decision.verdict
        risk_level = $investigationDetail.decision.risk_level
        measured_http_replays = $replayRequests.Count
        counterfactuals = @(
            $counterfactuals | ForEach-Object {
                [ordered]@{
                    scenario_id = $_.scenario_id
                    intervention = $_.intervention
                    verdict = $_.verdict
                    original_score = $_.original_score
                    counterfactual_score = $_.counterfactual_score
                    # The engine writes "Replayed ... under <intervention>: score
                    # x -> y"; the deterministic fallback writes "is predicted to
                    # restore ...". Recording it makes the difference auditable
                    # from the committed evidence alone.
                    rationale = $_.rationale
                }
            }
        )
        evidence_dir = $evidenceDir
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $resultFile = if ([System.IO.Path]::IsPathRooted($ResultPath)) {
        $ResultPath
    } else {
        Join-Path $repoRoot $ResultPath
    }
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $resultFile -Encoding utf8
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $workDir 'summary.json') -Encoding utf8

    Write-Host "`nP5 external-SUT evaluation OK" -ForegroundColor Green
    Write-Host "Evidence: $resultFile"
    Write-Host "Logs:     $workDir"
} catch {
    Write-Host "`nP5 external-SUT evaluation FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Logs: $workDir"
    throw
} finally {
    Stop-Tree $backendProcess.process
    Stop-Tree $sutProcess.process
}

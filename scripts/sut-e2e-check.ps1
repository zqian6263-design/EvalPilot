<#
.SYNOPSIS
    Prove that EvalPilot evaluates a real external HTTP SUT, not only its mock.

.DESCRIPTION
    Starts the public Haystack SUT in a separate process, points the backend at it
    through EVALPILOT_SUT_URL, and verifies four things with live API results:

      1. A v1.1-versus-v1.1 negative control reports no regression.
      2. A v1.0-versus-v1.1 run detects the known regressions.
      3. Counterfactual replay evidence also comes through the HTTP boundary.
      4. A cached run replays offline with the SUT stopped; an uncached run fails
         loudly when the SUT is unavailable instead of falling back to the mock.

    The script writes a machine-readable summary under .runtime/sut-e2e-*.
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8011,
    [int]$OfflineBackendPort = 8012,
    [int]$FailureBackendPort = 8013,
    [int]$SutPort = 8010,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPython)) { $venvPython = 'python' }
$runtimeRoot = Join-Path $repoRoot '.runtime'
$runToken = [guid]::NewGuid().ToString('N')
$workDir = Join-Path $runtimeRoot "sut-e2e-$runToken"
$null = New-Item -ItemType Directory -Path $workDir -Force
$dbPath = Join-Path $workDir 'evalpilot.db'
$cacheDir = Join-Path $workDir 'cache'
$failureCacheDir = Join-Path $workDir 'failure-cache'
$null = New-Item -ItemType Directory -Path $cacheDir -Force
$null = New-Item -ItemType Directory -Path $failureCacheDir -Force

$sutUrl = "http://127.0.0.1:$SutPort"
$failures = [System.Collections.Generic.List[string]]::new()
$processes = [System.Collections.Generic.List[object]]::new()
$summary = [ordered]@{
    started_at = (Get-Date).ToUniversalTime().ToString('o')
    sut_url = $sutUrl
    sut_engine = 'haystack-ai'
    database = $dbPath
    cache_dir = $cacheDir
}

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

function Api([string]$base, [string]$method, [string]$path, $body = $null) {
    $params = @{ Method = $method; Uri = "$base$path"; TimeoutSec = 30 }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ($body | ConvertTo-Json -Depth 12)
    }
    Invoke-RestMethod @params
}

function Start-EvalPilotBackend(
    [int]$port,
    [bool]$offline,
    [string]$sutCacheDir,
    [string]$label
) {
    $env:PYTHONPATH = $backendDir
    $env:EVALPILOT_DB_PATH = $dbPath
    $env:EVALPILOT_STEP_DELAY = '0'
    $env:EVALPILOT_SUT_URL = $sutUrl
    $env:EVALPILOT_SUT_CACHE_DIR = $sutCacheDir
    $env:EVALPILOT_SUT_OFFLINE = if ($offline) { 'true' } else { 'false' }
    $args = @(
        '-m', 'uvicorn', 'evalpilot.app:create_app', '--factory',
        '--host', '127.0.0.1', '--port', "$port", '--log-level', 'warning'
    )
    $started = Start-ProcessChecked `
        -name $label `
        -arguments $args `
        -workingDirectory $backendDir `
        -stdoutLog (Join-Path $workDir "$label.out.log") `
        -stderrLog (Join-Path $workDir "$label.err.log")
    if (-not (Wait-Http "http://127.0.0.1:$port/api/health" 45)) {
        throw "$label failed to start:`n$(Server-Tail $started.stdout $started.stderr)"
    }
    return $started
}

function Wait-Run([string]$apiBase, [string]$runId, [int]$seconds = $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    $detail = $null
    do {
        Start-Sleep -Milliseconds 250
        $detail = Api $apiBase GET "/runs/$runId"
        $status = $detail.run.status
    } while ($status -notin @('completed', 'failed', 'cancelled') -and (Get-Date) -lt $deadline)
    return $detail
}

function New-Run(
    [string]$apiBase,
    [string]$projectId,
    [string]$baseline,
    [string]$candidate,
    [int]$caseCount = 26
) {
    Api $apiBase POST '/runs' @{
        project_id = $projectId
        baseline_version = $baseline
        candidate_version = $candidate
        seed = 20260919
        case_count = $caseCount
    }
}

function Start-And-WaitRun([string]$apiBase, $run) {
    Api $apiBase POST "/runs/$($run.id)/start" | Out-Null
    Wait-Run $apiBase $run.id
}

$sutProcess = $null
$onlineBackend = $null
$offlineBackend = $null
$failureBackend = $null

try {
    Assert-PortFree $BackendPort
    Assert-PortFree $OfflineBackendPort
    Assert-PortFree $FailureBackendPort
    Assert-PortFree $SutPort

    Write-Host "`n-- Start the external SUT"
    $env:PYTHONPATH = $backendDir
    $sutProcess = Start-ProcessChecked `
        -name 'public-haystack-sut' `
        -arguments @('-m', 'uvicorn', 'evalpilot.sut.haystack_server:app', '--host', '127.0.0.1', '--port', "$SutPort", '--log-level', 'warning') `
        -workingDirectory $backendDir `
        -stdoutLog (Join-Path $workDir 'sut.out.log') `
        -stderrLog (Join-Path $workDir 'sut.err.log')
    $sutHealthy = Wait-Http "$sutUrl/health" 45
    $sutHealth = if ($sutHealthy) { Invoke-RestMethod -Uri "$sutUrl/health" -TimeoutSec 10 } else { $null }
    Step 'the public open-source Haystack SUT is healthy' ($sutHealthy -and $sutHealth.engine -eq 'haystack-ai') (Server-Tail $sutProcess.stdout $sutProcess.stderr)
    if (-not $sutHealthy) { throw 'public Haystack SUT did not become healthy' }
    $sutCapabilities = Invoke-RestMethod -Uri "$sutUrl/capabilities" -TimeoutSec 10
    Step 'the SUT advertises its executable capabilities' (
        $sutCapabilities.contract_version -eq '1.0' -and
        ($sutCapabilities.interventions -contains 'compression_disabled') -and
        ($sutCapabilities.interventions -contains 'security_guard_enabled')
    ) "interventions=$($sutCapabilities.interventions -join ',')"

    Write-Host "`n-- Start EvalPilot against the HTTP SUT"
    $onlineBackend = Start-EvalPilotBackend `
        -port $BackendPort -offline $false -sutCacheDir $cacheDir -label 'online-backend'
    $onlineApi = "http://127.0.0.1:$BackendPort/api"
    $project = Api $onlineApi POST '/projects' @{
        name = "External SUT $runToken"
        scenario = 'kb-qa'
    }

    Write-Host "`n-- Negative control: same candidate revision on both arms"
    $negativeRun = New-Run $onlineApi $project.id 'v1.1-candidate' 'v1.1-candidate'
    $negative = Start-And-WaitRun $onlineApi $negativeRun
    $negativeReport = Api $onlineApi GET "/runs/$($negativeRun.id)/report"
    Step 'the v1.1-vs-v1.1 run completes' ($negative.run.status -eq 'completed') $negative.run.status
    Step 'the negative control has no regressed scenarios' (@($negativeReport.metrics.regressed_scenarios).Count -eq 0) "regressed=$(@($negativeReport.metrics.regressed_scenarios).Count)"
    Step 'the negative control has no release-blocking finding' ($negativeReport.metrics.findings_by_severity.critical -eq $null) "critical=$($negativeReport.metrics.findings_by_severity.critical)"
    Step 'the negative control reports no regression' ($negativeReport.metrics.regression_detected -eq $false)
    Step 'the negative control mean delta is zero' ([double]$negativeReport.metrics.mean_difference -eq 0.0) "mean=$($negativeReport.metrics.mean_difference)"
    $summary.negative_control = $negativeReport.metrics

    Write-Host "`n-- Positive run: baseline versus candidate"
    $positiveRun = New-Run $onlineApi $project.id 'v1.0-baseline' 'v1.1-candidate'
    $positive = Start-And-WaitRun $onlineApi $positiveRun
    $positiveReport = Api $onlineApi GET "/runs/$($positiveRun.id)/report"
    Step 'the v1.0-vs-v1.1 run completes' ($positive.run.status -eq 'completed') $positive.run.status
    Step 'the external SUT run detects a regression' ($positiveReport.metrics.regression_detected -eq $true)
    Step 'the regression is negative' ([double]$positiveReport.metrics.mean_difference -lt 0) "mean=$($positiveReport.metrics.mean_difference)"
    Step 'the known eight scenarios regress' (@($positiveReport.metrics.regressed_scenarios).Count -ge 8) "count=$(@($positiveReport.metrics.regressed_scenarios).Count)"
    Step 'the run has evidence-linked findings' ($positive.finding_count -ge 8) "findings=$($positive.finding_count)"

    $requestVersions = @(
        $positive.evidence |
            Where-Object { $_.kind -eq 'trace' -and $_.payload.request } |
            ForEach-Object { [string]$_.payload.request.version } |
            Sort-Object -Unique
    )
    Step 'run evidence contains both real SUT revisions' (
        ($requestVersions -contains 'v1.0-baseline') -and
        ($requestVersions -contains 'v1.1-candidate')
    ) "versions=$($requestVersions -join ',')"
    $summary.positive_run = $positiveReport.metrics

    Write-Host "`n-- Counterfactual replay through the same HTTP boundary"
    $objective = 'Determine whether the external candidate is safe to ship, identify the root cause, and produce an evidence-backed release decision.'
    $investigation = Api $onlineApi POST '/investigations' @{
        run_id = $positiveRun.id
        objective = $objective
    }
    if ($investigation.status -eq 'queued') {
        Api $onlineApi POST "/investigations/$($investigation.id)/start" | Out-Null
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 400
        $investigationDetail = Api $onlineApi GET "/investigations/$($investigation.id)"
        $investigationStatus = $investigationDetail.investigation.status
    } while ($investigationStatus -notin @('completed', 'failed') -and (Get-Date) -lt $deadline)

    Step 'the external-SUT investigation completes' ($investigationStatus -eq 'completed') $investigationStatus
    $counterfactuals = @($investigationDetail.counterfactuals)
    Step 'the investigation replays every regressed scenario' ($counterfactuals.Count -ge 8) "replays=$($counterfactuals.Count)"
    Step 'every replay is evidence-linked' (@($counterfactuals | Where-Object { -not $_.evidence_ids }).Count -eq 0)

    $afterInvestigation = Api $onlineApi GET "/runs/$($positiveRun.id)"
    $replayTraceCount = @(
        $afterInvestigation.evidence |
            Where-Object {
                $_.kind -eq 'trace' -and
                $_.payload.request -and
                $_.payload.request.intervention -ne $null
            }
    ).Count
    Step 'counterfactual trace evidence comes from the HTTP SUT' ($replayTraceCount -ge 8) "traces=$replayTraceCount"
    $summary.investigation = @{
        status = $investigationStatus
        replays = $counterfactuals.Count
        http_replay_traces = $replayTraceCount
        verdict = $investigationDetail.decision.verdict
    }

    Write-Host "`n-- Stop the SUT and replay the cached workload offline"
    Stop-Tree $sutProcess.process
    $sutProcess = $null
    Stop-Tree $onlineBackend.process
    $onlineBackend = $null

    $offlineBackend = Start-EvalPilotBackend `
        -port $OfflineBackendPort -offline $true -sutCacheDir $cacheDir -label 'offline-backend'
    $offlineApi = "http://127.0.0.1:$OfflineBackendPort/api"
    $offlineRun = New-Run $offlineApi $project.id 'v1.0-baseline' 'v1.1-candidate'
    $offline = Start-And-WaitRun $offlineApi $offlineRun
    $offlineReport = Api $offlineApi GET "/runs/$($offlineRun.id)/report"
    Step 'the cached workload completes with the SUT stopped' ($offline.run.status -eq 'completed') $offline.run.status
    Step 'offline replay identifies the same regression' ($offlineReport.metrics.regression_detected -eq $true)
    Step 'offline replay reproduces the mean delta' (
        [math]::Abs([double]$offlineReport.metrics.mean_difference - [double]$positiveReport.metrics.mean_difference) -lt 0.000001
    ) "offline=$($offlineReport.metrics.mean_difference) online=$($positiveReport.metrics.mean_difference)"
    $summary.offline_replay = $offlineReport.metrics
    Stop-Tree $offlineBackend.process
    $offlineBackend = $null

    Write-Host "`n-- No-SUT failure must not fall back to the mock"
    $failureBackend = Start-EvalPilotBackend `
        -port $FailureBackendPort -offline $false -sutCacheDir $failureCacheDir -label 'failure-backend'
    $failureApi = "http://127.0.0.1:$FailureBackendPort/api"
    $failureRun = New-Run $failureApi $project.id 'v1.0-baseline' 'v1.1-candidate' 1
    $failure = Start-And-WaitRun $failureApi $failureRun
    $failureStream = Invoke-WebRequest -Uri "$failureApi/runs/$($failureRun.id)/events?fmt=ndjson&follow=false" -TimeoutSec 30 -UseBasicParsing
    $eventMessage = (@(
        $failureStream.Content -split "`n" |
            Where-Object { $_.Trim() } |
            ForEach-Object { (ConvertFrom-Json $_).message }
    ) -join ' ')
    $failureLog = if (Test-Path $failureBackend.stderr) { Get-Content -LiteralPath $failureBackend.stderr -Raw } else { '' }
    $failureMessage = "$eventMessage $failureLog".Trim()
    Step 'an uncached run fails when the SUT is unavailable' ($failure.run.status -eq 'failed') $failure.run.status
    Step 'the failure names the external SUT failure' (
        $failureMessage -match 'SUT returned HTTP|SUT request failed|SutError|Connection'
    ) $failureMessage
    $summary.unavailable_sut = @{
        status = $failure.run.status
        message = $failureMessage
    }

    if ($failures.Count -gt 0) {
        throw "External-SUT E2E failed: $($failures -join '; ')"
    }

    $summary.status = 'passed'
    $summary.completed_at = (Get-Date).ToUniversalTime().ToString('o')
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $workDir 'summary.json') -Encoding utf8
    Write-Host "`nExternal-SUT E2E OK" -ForegroundColor Green
    Write-Host "Evidence: $(Join-Path $workDir 'summary.json')"
} catch {
    $summary.status = 'failed'
    $summary.error = $_.Exception.Message
    $summary.completed_at = (Get-Date).ToUniversalTime().ToString('o')
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $workDir 'summary.json') -Encoding utf8
    Write-Host "`nExternal-SUT E2E FAILED: $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    Stop-Tree $failureBackend.process
    Stop-Tree $offlineBackend.process
    Stop-Tree $onlineBackend.process
    Stop-Tree $sutProcess.process
}

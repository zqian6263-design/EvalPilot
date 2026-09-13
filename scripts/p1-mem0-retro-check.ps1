[CmdletBinding()]
param(
    [int]$BackendPort = 8130,
    [int]$SutPort = 8120,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$integrationDir = Join-Path $repoRoot 'integrations/mem0_retro'
$workloadFile = Join-Path $integrationDir 'workload.json'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPython)) { $venvPython = 'python' }
$runtimeRoot = Join-Path $repoRoot '.runtime'
$runToken = [guid]::NewGuid().ToString('N')
$workDir = Join-Path $runtimeRoot "p1-mem0-retro-$runToken"
$null = New-Item -ItemType Directory -Path $workDir -Force

$baseUrl = "http://127.0.0.1:$BackendPort"
$api = "$baseUrl/api"
$sutUrl = "http://127.0.0.1:$SutPort"
$failures = [System.Collections.Generic.List[string]]::new()
$sutProcess = $null
$backendProcess = $null

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
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    return $false
}

function Stop-Tree($process) {
    if ($null -eq $process) { return }
    if (-not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
    }
}

function Api([string]$method, [string]$path, $body = $null) {
    $params = @{ Method = $method; Uri = "$api$path"; TimeoutSec = 60 }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ($body | ConvertTo-Json -Depth 12)
    }
    Invoke-RestMethod @params
}

function New-Run([string]$projectId, [string]$baseline, [string]$candidate) {
    Api POST '/runs' @{
        project_id = $projectId
        baseline_version = $baseline
        candidate_version = $candidate
        seed = 20260919
        case_count = 6
    }
}

function Start-And-WaitRun($run) {
    Api POST "/runs/$($run.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $detail = Api GET "/runs/$($run.id)"
    } while ($detail.run.status -in @('queued', 'planning', 'executing', 'evaluating') -and (Get-Date) -lt $deadline)
    if ($detail.run.status -ne 'completed') {
        throw "run $($run.id) did not complete: $($detail.run.status)"
    }
    $detail
}
try {
    Write-Host "-- Prepare the public mem0 adapter"
    if (-not (Test-Path (Join-Path $integrationDir 'node_modules'))) {
        & npm ci --prefix $integrationDir
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    }

    Write-Host "-- Start the deterministic mem0 HTTP SUT"
    $sutJob = Start-Job -ScriptBlock {
        param($dir, $serverPort)
        Set-Location $dir
        $env:MEM0_RETRO_PORT = "$serverPort"
        node server.mjs
    } -ArgumentList $integrationDir, $SutPort
    $sutHealthy = Wait-Http "$sutUrl/health" 60
    Step 'public mem0 HTTP SUT is healthy' $sutHealthy
    if (-not $sutHealthy) { throw 'mem0 SUT did not become healthy' }

    $capabilities = Invoke-RestMethod "$sutUrl/capabilities"
    Step 'SUT advertises both published package versions' (
        ($capabilities.versions -contains 'mem0ai-3.1.0') -and
        ($capabilities.versions -contains 'mem0ai-3.1.1')
    ) "versions=$($capabilities.versions -join ',')"
    Step 'SUT advertises the identity replay intervention' ($capabilities.interventions -contains 'identity_metadata_stripped')

    Write-Host "-- Start EvalPilot with the external workload"
    $backendJob = Start-Job -ScriptBlock {
        param($root, $python, $backendPort, $externalSutUrl, $workload, $work)
        Set-Location $root
        $env:PYTHONPATH = (Join-Path $root 'backend')
        $env:EVALPILOT_DB_PATH = (Join-Path $work 'evalpilot.db')
        $env:EVALPILOT_ARTIFACTS_DIR = (Join-Path $work 'artifacts')
        $env:EVALPILOT_SUT_URL = $externalSutUrl
        $env:EVALPILOT_SUT_DISCOVERY = 'true'
        $env:EVALPILOT_SUT_CACHE_DIR = (Join-Path $work 'cache')
        $env:EVALPILOT_WORKLOAD_FILE = $workload
        & $python -m uvicorn evalpilot.app:create_app --factory --host 127.0.0.1 --port $backendPort --log-level warning
    } -ArgumentList $repoRoot, $venvPython, $BackendPort, $sutUrl, $workloadFile, $workDir
    $backendHealthy = Wait-Http "$api/health" 60
    Step 'EvalPilot backend is healthy' $backendHealthy
    if (-not $backendHealthy) { throw 'EvalPilot backend did not become healthy' }

    $project = Api POST '/projects' @{ name = 'mem0 public retrospective'; scenario = 'mem0-retrospective' }

    Write-Host "-- Negative control: fixed version against itself"
    $controlRun = New-Run $project.id 'mem0ai-3.1.1' 'mem0ai-3.1.1'
    $controlDetail = Start-And-WaitRun $controlRun
    $controlReport = Api GET "/runs/$($controlRun.id)/report"
    Step 'same-version control reports no regression' (
        $controlReport.metrics.regression_detected -eq $false -and @($controlReport.metrics.regressed_scenarios).Count -eq 0
    ) "direction=$($controlReport.metrics.direction)"

    Write-Host "-- Retrospective: fixed 3.1.1 -> published buggy 3.1.0"
    $positiveRun = New-Run $project.id 'mem0ai-3.1.1' 'mem0ai-3.1.0'
    $positiveDetail = Start-And-WaitRun $positiveRun
    $positiveReport = Api GET "/runs/$($positiveRun.id)/report"
    $regressed = @($positiveReport.metrics.regressed_scenarios)
    $controls = @($positiveReport.metrics.control_scenarios)
    Step 'EvalPilot confirms a real regression' ($positiveReport.metrics.regression_detected -eq $true)
    Step 'all three public identity failures are found' ($regressed.Count -eq 3) ($regressed -join ',')
    Step 'three control scenarios remain unchanged' ($controls.Count -eq 3) ($controls -join ',')
    Step 'paired interval is below the regression threshold' (
        [double]$positiveReport.metrics.ci_upper -lt [double]$positiveReport.metrics.regression_threshold
    ) "CI=[$($positiveReport.metrics.ci_lower), $($positiveReport.metrics.ci_upper)]"

    Write-Host "-- Autonomous investigation and counterfactual replay"
    $investigation = Api POST '/investigations' @{
        run_id = $positiveRun.id
        objective = 'Diagnose the public mem0 revision gap without preclassifying the failing scenarios.'
    }
    Api POST "/investigations/$($investigation.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $investigationDetail = Api GET "/investigations/$($investigation.id)"
    } while ($investigationDetail.investigation.status -in @('queued', 'running') -and (Get-Date) -lt $deadline)

    $counterfactuals = @($investigationDetail.counterfactuals)
    Step 'investigation completes' ($investigationDetail.investigation.status -eq 'completed')
    Step 'every regressed scenario is replayed' ($counterfactuals.Count -eq 3) "replays=$($counterfactuals.Count)"
    Step 'every replay uses the executable identity intervention' (
        @($counterfactuals | Where-Object { $_.intervention -ne 'identity_metadata_stripped' }).Count -eq 0
    )
    Step 'every replay confirms the root cause' (
        @($counterfactuals | Where-Object { $_.verdict -ne 'root_cause' }).Count -eq 0
    )
    Step 'release decision is BLOCK / CRITICAL' (
        $investigationDetail.decision.verdict -eq 'block' -and $investigationDetail.decision.risk_level -eq 'critical'
    )
    Step 'every counterfactual is evidence-linked' (
        @($counterfactuals | Where-Object { @($_.evidence_ids).Count -eq 0 }).Count -eq 0
    )

    $reportMarkdown = (Invoke-WebRequest -Uri "$api/investigations/$($investigation.id)/report.md" -TimeoutSec 30 -UseBasicParsing).Content
    $reportPath = Join-Path $workDir 'investigation-report.md'
    [System.IO.File]::WriteAllText($reportPath, $reportMarkdown, [System.Text.UTF8Encoding]::new($false))

    if ($failures.Count -gt 0) { throw "P1 mem0 retrospective failed: $($failures -join '; ')" }

    $summary = [ordered]@{
        status = 'passed'
        workload = 'mem0-tenant-isolation-retrospective'
        source_issue = 'https://github.com/mem0ai/mem0/issues/6342'
        source_fix = 'https://github.com/mem0ai/mem0/pull/6343'
        baseline_version = 'mem0ai-3.1.1'
        candidate_version = 'mem0ai-3.1.0'
        regression_run_id = $positiveRun.id
        investigation_id = $investigation.id
        matched_scenarios = $positiveReport.metrics.scenario_count
        regressed_scenarios = $regressed
        control_scenarios = $controls
        mean_difference = $positiveReport.metrics.mean_difference
        ci = @($positiveReport.metrics.ci_lower, $positiveReport.metrics.ci_upper)
        decision = $investigationDetail.decision.verdict
        risk_level = $investigationDetail.decision.risk_level
        counterfactuals = @(
            $counterfactuals | ForEach-Object {
                @{ scenario_id = $_.scenario_id; intervention = $_.intervention; verdict = $_.verdict; original_score = $_.original_score; counterfactual_score = $_.counterfactual_score }
            }
        )
        report = $reportPath
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $workDir 'summary.json') -Encoding utf8
    Write-Host "`nP1 mem0 retrospective OK" -ForegroundColor Green
    Write-Host "Evidence: $(Join-Path $workDir 'summary.json')"
} catch {
    Write-Host "`nP1 mem0 retrospective FAILED: $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    if ($backendJob) { Stop-Job $backendJob -ErrorAction SilentlyContinue; Remove-Job $backendJob -Force -ErrorAction SilentlyContinue }
    if ($sutJob) { Stop-Job $sutJob -ErrorAction SilentlyContinue; Remove-Job $sutJob -Force -ErrorAction SilentlyContinue }
}

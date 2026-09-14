[CmdletBinding()]
param(
    [int]$BackendPort = 8160,
    [int]$SutPort = 8135,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$integrationDir = Join-Path $repoRoot 'integrations/mcp_retro'
$workloadFile = Join-Path $integrationDir 'workload.json'
$requirementsV1 = Join-Path $integrationDir 'requirements-v1.txt'
$requirementsV2 = Join-Path $integrationDir 'requirements-v2.txt'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPython)) { $venvPython = 'python' }
$runtimeRoot = Join-Path $repoRoot '.runtime'
$runToken = [guid]::NewGuid().ToString('N')
$workDir = Join-Path $runtimeRoot "p4-mcp-retro-$runToken"
$null = New-Item -ItemType Directory -Path $workDir -Force
$v1Runtime = Join-Path $runtimeRoot 'p4-mcp-v1'
$v2Runtime = Join-Path $runtimeRoot 'p4-mcp-v2'
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

function Prepare-McpRuntime([string]$directory, [string]$requirements) {
    $python = Join-Path $directory 'Scripts/python.exe'
    if (-not (Test-Path $python)) {
        & python -m venv $directory
        if ($LASTEXITCODE -ne 0) { throw "failed to create MCP runtime: $directory" }
    }
    & $python -m pip install --quiet --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "failed to install MCP requirements: $requirements" }
    return $python
}

function Api([string]$method, [string]$path, $body = $null) {
    $params = @{ Method = $method; Uri = "$api$path"; TimeoutSec = 60 }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ($body | ConvertTo-Json -Depth 12)
    }
    Invoke-RestMethod @params
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

function New-Run([string]$projectId, [string]$baseline, [string]$candidate) {
    Api POST '/runs' @{
        project_id = $projectId
        baseline_version = $baseline
        candidate_version = $candidate
        seed = 20260919
        case_count = 6
    }
}

try {
    Write-Host '-- Prepare isolated public MCP runtimes'
    $v1Python = Prepare-McpRuntime $v1Runtime $requirementsV1
    $v2Python = Prepare-McpRuntime $v2Runtime $requirementsV2
    $v1Version = (& $v1Python -c "import importlib.metadata as m; print(m.version('mcp'))").Trim()
    $v2Version = (& $v2Python -c "import importlib.metadata as m; print(m.version('mcp'))").Trim()
    Step 'v1 runtime is pinned to the published impaired release' ($v1Version -eq '1.30.0') "mcp=$v1Version"
    Step 'v2 runtime is pinned to the published fixed release' ($v2Version -eq '2.2.0') "mcp=$v2Version"

    Write-Host '-- Start the version-isolated MCP HTTP SUT'
    $sutJob = Start-Job -ScriptBlock {
        param($root, $python, $port, $v1, $v2)
        Set-Location $root
        $env:PYTHONPATH = (Join-Path $root 'integrations')
        $env:EVALPILOT_MCP_V1_PYTHON = $v1
        $env:EVALPILOT_MCP_V2_PYTHON = $v2
        $env:EVALPILOT_MCP_PROBE_TIMEOUT_SECONDS = '60'
        & $python -m uvicorn mcp_retro.server:app --host 127.0.0.1 --port $port --log-level warning
    } -ArgumentList $repoRoot, $venvPython, $SutPort, $v1Python, $v2Python
    $sutHealthy = Wait-Http "$sutUrl/health" 60
    Step 'MCP retrospective HTTP SUT is healthy' $sutHealthy
    if (-not $sutHealthy) { throw 'MCP retrospective SUT did not become healthy' }

    $capabilities = Invoke-RestMethod "$sutUrl/capabilities"
    Step 'SUT advertises both isolated MCP releases' (
        ($capabilities.versions -contains 'mcp-1.30.0') -and
        ($capabilities.versions -contains 'mcp-2.2.0')
    ) "versions=$($capabilities.versions -join ',')"
    Step 'SUT advertises the v2 error-path intervention' ($capabilities.interventions -contains 'mcp_v2_error_path_enabled')

    $goodProbe = Invoke-RestMethod -Method Post -Uri "$sutUrl/v1/answer" -ContentType 'application/json' -Body (@{
        run_id = 'probe-run'; test_case_id = 'probe-v2'; scenario_id = 'protocol-error-code'
        question = 'preserve the structured code'; version = 'mcp-2.2.0'; intervention = $null
    } | ConvertTo-Json)
    $badProbe = Invoke-RestMethod -Method Post -Uri "$sutUrl/v1/answer" -ContentType 'application/json' -Body (@{
        run_id = 'probe-run'; test_case_id = 'probe-v1'; scenario_id = 'protocol-error-code'
        question = 'preserve the structured code'; version = 'mcp-1.30.0'; intervention = $null
    } | ConvertTo-Json)
    Step 'published v2 preserves the MCP protocol error code' ($goodProbe.answer -match 'structured_code=-32000') $goodProbe.answer
    Step 'published v1 loses the MCP protocol error code' ($badProbe.answer -match 'structured_code=none') $badProbe.answer

    Write-Host '-- Start EvalPilot against the external MCP workload'
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
        $env:EVALPILOT_STEP_DELAY = '0'
        & $python -m uvicorn evalpilot.app:create_app --factory --host 127.0.0.1 --port $backendPort --log-level warning
    } -ArgumentList $repoRoot, $venvPython, $BackendPort, $sutUrl, $workloadFile, $workDir
    $backendHealthy = Wait-Http "$api/health" 60
    Step 'EvalPilot backend is healthy' $backendHealthy
    if (-not $backendHealthy) { throw 'EvalPilot backend did not become healthy' }

    $project = Api POST '/projects' @{ name = 'MCP public retrospective'; scenario = 'mcp-error-propagation' }

    Write-Host '-- Same-version control: 2.2.0 -> 2.2.0'
    $controlRun = New-Run $project.id 'mcp-2.2.0' 'mcp-2.2.0'
    $controlDetail = Start-And-WaitRun $controlRun
    $controlReport = Api GET "/runs/$($controlRun.id)/report"
    Step 'same-version control does not report a regression' (
        $controlReport.metrics.regression_detected -eq $false -and @($controlReport.metrics.regressed_scenarios).Count -eq 0
    ) "direction=$($controlReport.metrics.direction)"

    Write-Host '-- Retrospective: fixed 2.2.0 -> published v1 1.30.0'
    $positiveRun = New-Run $project.id 'mcp-2.2.0' 'mcp-1.30.0'
    $positiveDetail = Start-And-WaitRun $positiveRun
    $positiveReport = Api GET "/runs/$($positiveRun.id)/report"
    $regressed = @($positiveReport.metrics.regressed_scenarios)
    $controls = @($positiveReport.metrics.control_scenarios)
    $traceEvidence = @($positiveDetail.evidence | Where-Object { $_.kind -eq 'trace' })
    Step 'EvalPilot confirms a real MCP regression' ($positiveReport.metrics.regression_detected -eq $true)
    Step 'all three protocol observables are found' ($regressed.Count -eq 3) ($regressed -join ',')
    Step 'three control scenarios remain unchanged' ($controls.Count -eq 3) ($controls -join ',')
    Step 'paired interval is below the regression threshold' (
        [double]$positiveReport.metrics.ci_upper -lt [double]$positiveReport.metrics.regression_threshold
    ) "CI=[$($positiveReport.metrics.ci_lower), $($positiveReport.metrics.ci_upper)]"
    Step 'every executed case has a persisted SUT trace' ($traceEvidence.Count -eq 12) "traces=$($traceEvidence.Count)"

    Write-Host '-- Autonomous investigation and v2 counterfactual replay'
    $investigation = Api POST '/investigations' @{
        run_id = $positiveRun.id
        objective = 'Diagnose the public MCP error-propagation regression without preclassifying the observable failure.'
    }
    Api POST "/investigations/$($investigation.id)/start" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $investigationDetail = Api GET "/investigations/$($investigation.id)"
    } while ($investigationDetail.investigation.status -in @('queued', 'running') -and (Get-Date) -lt $deadline)

    $counterfactuals = @($investigationDetail.counterfactuals)
    Step 'investigation completes' ($investigationDetail.investigation.status -eq 'completed')
    Step 'every regressed observable is replayed' ($counterfactuals.Count -eq 3) "replays=$($counterfactuals.Count)"
    Step 'every replay uses the executable MCP v2 intervention' (
        @($counterfactuals | Where-Object { $_.intervention -ne 'mcp_v2_error_path_enabled' }).Count -eq 0
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

    if ($failures.Count -gt 0) { throw "P4 MCP retrospective failed: $($failures -join '; ')" }

    $summary = [ordered]@{
        status = 'passed'
        workload = 'mcp-error-propagation-retrospective'
        source_issue = 'https://github.com/modelcontextprotocol/python-sdk/issues/2770'
        public_versions = @('mcp==1.30.0', 'mcp==2.2.0')
        baseline_version = 'mcp-2.2.0'
        candidate_version = 'mcp-1.30.0'
        regression_run_id = $positiveRun.id
        control_run_id = $controlRun.id
        investigation_id = $investigation.id
        matched_scenarios = $positiveReport.metrics.scenario_count
        regressed_scenarios = $regressed
        control_scenarios = $controls
        trace_evidence = $traceEvidence.Count
        mean_difference = $positiveReport.metrics.mean_difference
        ci = @($positiveReport.metrics.ci_lower, $positiveReport.metrics.ci_upper)
        decision = $investigationDetail.decision.verdict
        risk_level = $investigationDetail.decision.risk_level
        counterfactuals = @(
            $counterfactuals | ForEach-Object {
                @{
                    scenario_id = $_.scenario_id
                    intervention = $_.intervention
                    verdict = $_.verdict
                    original_score = $_.original_score
                    counterfactual_score = $_.counterfactual_score
                }
            }
        )
        report = $reportPath
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $resultPath = Join-Path $repoRoot 'docs/P4_MCP_RESULT.json'
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $resultPath -Encoding utf8
    $summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $workDir 'summary.json') -Encoding utf8
    Write-Host "`nP4 MCP retrospective OK" -ForegroundColor Green
    Write-Host "Evidence: $resultPath"
} catch {
    Write-Host "`nP4 MCP retrospective FAILED: $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    if ($backendJob) { Stop-Job $backendJob -ErrorAction SilentlyContinue; Remove-Job $backendJob -Force -ErrorAction SilentlyContinue }
    if ($sutJob) { Stop-Job $sutJob -ErrorAction SilentlyContinue; Remove-Job $sutJob -Force -ErrorAction SilentlyContinue }
}

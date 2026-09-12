<#
.SYNOPSIS
    Prove the EvalPilot stack works end to end, over real HTTP.

.DESCRIPTION
    Drives the whole product path against a running service and fails on the
    first thing that is not true:

      1. start the stack (reusing whatever is already healthy), or reuse -StackOnly;
      2. create a project and a run, start it, poll to a terminal status;
      3. read the report and check the metrics it claims are internally consistent;
      4. check every finding links to evidence rows that exist in the run;
      5. check the frontend answers and serves the console;
      6. screenshot the console when Chrome or Edge is installed;
      7. stop only the processes this script started.

    The assertions are chosen so that a passing run means something. A run that
    "returns 200" proves nothing; these checks require that the deliberately
    regressed scenarios are actually detected, that the reported pass rate
    matches the case statuses, and that no finding cites evidence that is not
    there - which is the claim `docs/SPEC.md` makes on the product's behalf.

    Nothing is mocked. Every value is read from the running service.

.PARAMETER BackendPort
    Backend port. Default 8000.

.PARAMETER FrontendPort
    Frontend port. Default 5173.

.PARAMETER ScreenshotPath
    Where to write the console screenshot. Default .runtime/e2e-console.png.

.PARAMETER KeepRunning
    Leave a stack this script started up after the checks finish.

.PARAMETER SkipScreenshot
    Do not attempt a browser capture.

.PARAMETER TimeoutSeconds
    How long to wait for a run to finish. Default 90.

.EXAMPLE
    .\scripts\e2e-check.ps1
    .\scripts\e2e-check.ps1 -KeepRunning
    .\scripts\e2e-check.ps1 -SkipScreenshot
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$ScreenshotPath,
    [switch]$KeepRunning,
    [switch]$SkipScreenshot,
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot '.runtime'
if (-not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir | Out-Null }
if (-not $ScreenshotPath) { $ScreenshotPath = Join-Path $runtimeDir 'e2e-console.png' }

$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"
$api = "$backendUrl/api"

$script:checks = 0
$script:failures = @()
$script:notes = @()

# ------------------------------------------------------------------ output --

function Section([string]$title) {
    Write-Host ''
    Write-Host "-- $title" -ForegroundColor Cyan
}

function Check([string]$label, [bool]$ok, [string]$detail = '') {
    $script:checks += 1
    if ($ok) {
        Write-Host "  PASS  $label" -ForegroundColor Green
    } else {
        Write-Host "  FAIL  $label" -ForegroundColor Red
        if ($detail) { Write-Host "        $detail" -ForegroundColor DarkGray }
        $script:failures += $label
    }
    # No return value: an unconsumed one would print `True` under every PASS.
}

function Note([string]$message) {
    Write-Host "  note  $message" -ForegroundColor DarkGray
    $script:notes += $message
}

function Invoke-Api {
    param(
        [string]$Method = 'GET',
        [string]$Path,
        $Body = $null,
        [int]$TimeoutSec = 15
    )
    $params = @{
        Method      = $Method
        Uri         = "$api$Path"
        TimeoutSec  = $TimeoutSec
        UseBasicParsing = $true
        ErrorAction = 'Stop'
    }
    if ($null -ne $Body) {
        $params['Body'] = ($Body | ConvertTo-Json -Depth 8)
        $params['ContentType'] = 'application/json'
    }
    $response = Invoke-WebRequest @params
    if ([string]::IsNullOrWhiteSpace($response.Content)) { return $null }
    return $response.Content | ConvertFrom-Json
}

# ------------------------------------------------------------------- stack --

Section 'Stack'

$stackScript = Join-Path $PSScriptRoot 'start-all.ps1'
$startedHere = $false

# Only a stack this invocation started may be stopped by it. start-all records
# what it launched; if it started nothing, there is nothing of ours to clean up.
$pidFile = Join-Path $runtimeDir 'pids.json'

& $stackScript -BackendPort $BackendPort -FrontendPort $FrontendPort -TimeoutSeconds 90
# `&` on a -File script does not reliably reset $LASTEXITCODE, so success is
# judged by the thing we actually care about: is the service answering?
$backendUp = $false
try {
    $probe = Invoke-WebRequest -Uri "$backendUrl/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $backendUp = $probe.StatusCode -eq 200
} catch { $backendUp = $false }

if (-not $backendUp) {
    Write-Host "start-all.ps1 did not bring the backend up; cannot continue." -ForegroundColor Red
    exit 1
}

$after = if (Test-Path $pidFile) { Get-Content -Raw $pidFile | ConvertFrom-Json } else { $null }
foreach ($key in @('backend', 'frontend')) {
    $entry = $after.$key
    if ($null -ne $entry -and -not $entry.adopted) { $startedHere = $true }
}
if ($startedHere) {
    Note 'start-all started at least one process; this check will stop only those.'
} else {
    Note 'start-all started nothing (everything was already up); this check will stop nothing.'
}

# ------------------------------------------------------------------- health --

Section 'Health'

try {
    $health = Invoke-Api -Path '/health'
    Check 'GET /api/health answers with status ok' ($health.status -eq 'ok') "status=$($health.status)"
    Note "backend version $($health.version)"
} catch {
    Check 'GET /api/health answers' $false $_.Exception.Message
    exit 1
}

# ------------------------------------------------------- create, start, poll --

Section 'Run lifecycle'

$project = $null
$run = $null
try {
    # Reuse the demo project when it exists so repeated checks do not litter
    # the database with projects that mean the same thing.
    $projects = Invoke-Api -Path '/projects'
    $project = $projects | Where-Object { $_.name -eq 'Enterprise Knowledge Base QA' } | Select-Object -First 1
    if (-not $project) {
        $project = Invoke-Api -Method POST -Path '/projects' -Body @{
            name     = 'Enterprise Knowledge Base QA'
            scenario = 'kb-qa'
        }
    }
    Check 'a project exists for the demo' ($null -ne $project.id) "id=$($project.id)"
} catch {
    Check 'create or reuse the demo project' $false $_.Exception.Message
}

if ($project) {
    try {
        $run = Invoke-Api -Method POST -Path '/runs' -Body @{
            project_id        = $project.id
            baseline_version  = 'v1.0-baseline'
            candidate_version = 'v1.1-candidate'
            seed              = 20260919
            case_count        = 26
        }
        Check 'POST /api/runs creates a queued run' ($run.status -eq 'queued') "status=$($run.status)"
    } catch {
        Check 'POST /api/runs creates a run' $false $_.Exception.Message
    }
}

if ($run) {
    try {
        $started = Invoke-Api -Method POST -Path "/runs/$($run.id)/start"
        Check 'POST /api/runs/{id}/start accepts the run' ($null -ne $started.id) "status=$($started.status)"
    } catch {
        Check 'POST /api/runs/{id}/start accepts the run' $false $_.Exception.Message
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $status = 'queued'
    while ((Get-Date) -lt $deadline) {
        $current = Invoke-Api -Path "/runs/$($run.id)"
        $status = $current.run.status
        if (@('completed', 'failed', 'cancelled') -contains $status) { break }
        Start-Sleep -Milliseconds 500
    }
    Check 'the run reaches a terminal status' ($status -eq 'completed') "settled at '$status'"
    Note "run $($run.id) finished as '$status'"
}

# -------------------------------------------------------------------- detail --

$detail = $null
if ($run) {
    Section 'Run detail'

    $detail = Invoke-Api -Path "/runs/$($run.id)"

    # The envelope, not a flat Run - this is the shape the adapter normalises.
    Check 'GET /api/runs/{id} returns the run envelope' ($null -ne $detail.run.id) 'missing .run'
    Check 'the detail carries test cases' ($detail.test_cases.Count -gt 0) "count=$($detail.test_cases.Count)"
    Check 'the detail carries evidence' ($detail.evidence.Count -gt 0) "count=$($detail.evidence.Count)"
    Check 'the detail reports an evidence count' ($detail.evidence_count -gt 0) "evidence_count=$($detail.evidence_count)"
    Check 'the evidence count matches the rows returned' ($detail.evidence_count -eq $detail.evidence.Count) `
        "envelope=$($detail.evidence_count) rows=$($detail.evidence.Count)"

    $versions = $detail.test_cases | Group-Object version | ForEach-Object { $_.Name }
    Check 'both versions were executed' ($versions -contains 'baseline' -and $versions -contains 'candidate') `
        "versions=$($versions -join ',')"

    # Pairing: the adapter matches on input.scenario_id, so a run whose pairs
    # are incomplete would leave the console showing fewer cases than the run
    # executed. Assert the pairing is total.
    $scenarioIds = @{}
    foreach ($case in $detail.test_cases) {
        $sid = $case.input.scenario_id
        if (-not $scenarioIds.ContainsKey($sid)) { $scenarioIds[$sid] = @{ baseline = 0; candidate = 0 } }
        $scenarioIds[$sid][$case.version] += 1
    }
    $unpaired = @($scenarioIds.GetEnumerator() | Where-Object {
        $_.Value.baseline -ne 1 -or $_.Value.candidate -ne 1
    })
    Check 'every scenario has exactly one case per version' ($unpaired.Count -eq 0) `
        "unpaired: $($unpaired.Name -join ',')"
    Note "$($scenarioIds.Count) matched scenarios"
}

# -------------------------------------------------------------------- report --

$report = $null
if ($run) {
    Section 'Report'

    try {
        $report = Invoke-Api -Path "/runs/$($run.id)/report"
        Check 'GET /api/runs/{id}/report answers' ($null -ne $report.id) 'no report id'
    } catch {
        Check 'GET /api/runs/{id}/report answers' $false $_.Exception.Message
    }
}

if ($report -and $detail) {
    $metrics = $report.metrics

    Check 'the report states whether a regression was detected' `
        ($null -ne $metrics.regression_detected) 'metrics.regression_detected missing'
    Check 'a regression is detected in the seeded demo' ($metrics.regression_detected -eq $true) `
        "regression_detected=$($metrics.regression_detected)"
    Check 'the summary names the regressed scenarios' `
        ($report.summary -match 'regressed') "summary=$($report.summary)"

    # The reported pass rate must match the case statuses it was computed from.
    # If these disagree, one of the two is lying and the console would show it.
    $candidateCases = @($detail.test_cases | Where-Object { $_.version -eq 'candidate' })
    $candidatePassed = @($candidateCases | Where-Object { $_.status -eq 'passed' }).Count
    $derivedRate = if ($candidateCases.Count -gt 0) {
        [math]::Round($candidatePassed / $candidateCases.Count, 4)
    } else { 0 }
    Check 'the reported candidate pass rate matches the case statuses' `
        ([math]::Abs([double]$metrics.candidate_pass_rate - $derivedRate) -lt 0.001) `
        "reported=$($metrics.candidate_pass_rate) derived=$derivedRate ($candidatePassed/$($candidateCases.Count))"

    $baselineCases = @($detail.test_cases | Where-Object { $_.version -eq 'baseline' })
    $baselinePassed = @($baselineCases | Where-Object { $_.status -eq 'passed' }).Count
    Check 'the baseline passes every seeded case' ($baselinePassed -eq $baselineCases.Count) `
        "$baselinePassed/$($baselineCases.Count) passed"

    Check 'the reported matched count matches the paired scenarios' `
        ([int]$metrics.matched_scenarios -eq $scenarioIds.Count) `
        "reported=$($metrics.matched_scenarios) paired=$($scenarioIds.Count)"

    Check 'the report reports findings by severity' `
        ($null -ne $metrics.findings_by_severity) 'metrics.findings_by_severity missing'
}

# ------------------------------------------------------------------ findings --

if ($report -and $detail) {
    Section 'Findings and evidence links'

    $evidenceIds = @{}
    foreach ($item in $detail.evidence) { $evidenceIds[$item.id] = $true }

    Check 'the report carries findings' ($report.findings.Count -gt 0) "count=$($report.findings.Count)"

    $danglingTotal = 0
    $withoutEvidence = 0
    $withoutCase = 0
    foreach ($finding in $report.findings) {
        $dangling = @($finding.evidence_ids | Where-Object { -not $evidenceIds.ContainsKey($_) })
        $danglingTotal += $dangling.Count
        if (@($finding.evidence_ids).Count -eq 0) { $withoutEvidence += 1 }
        if (-not $finding.test_case_id) { $withoutCase += 1 } else {
            $caseExists = @($detail.test_cases | Where-Object { $_.id -eq $finding.test_case_id }).Count -eq 1
            if (-not $caseExists) { $withoutCase += 1 }
        }
    }

    # This is the claim docs/SPEC.md makes: every finding links to evidence.
    Check 'every finding cites at least one evidence row' ($withoutEvidence -eq 0) `
        "$withoutEvidence finding(s) cite nothing"
    Check 'every cited evidence id resolves to a row in the run' ($danglingTotal -eq 0) `
        "$danglingTotal dangling evidence id(s)"
    Check 'every finding names a test case that exists in the run' ($withoutCase -eq 0) `
        "$withoutCase finding(s) reference a missing case"

    Check 'every finding states a recommendation' `
        (@($report.findings | Where-Object { -not $_.recommendation }).Count -eq 0) `
        'a finding has no recommendation'

    $severities = @($report.findings | ForEach-Object { $_.severity } | Sort-Object -Unique)
    Check 'findings are graded by severity' ($severities.Count -gt 0) 'no severities'
    Note "findings: $($report.findings.Count) ($($severities -join ', '))"
}

# ----------------------------------------------------------------- frontend --

Section 'Frontend'

try {
    $page = Invoke-WebRequest -Uri "$frontendUrl/" -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
    Check 'the console serves HTML' ($page.StatusCode -eq 200) "status=$($page.StatusCode)"
    Check 'the console HTML mounts the app' ($page.Content -match 'id="root"') 'root element missing'
} catch {
    Check 'the frontend answers' $false $_.Exception.Message
}

try {
    # The browser talks to /api through the dev server's proxy. If the proxy is
    # misconfigured the page loads and every request fails, which looks like a
    # UI bug from the outside - so check the proxied path explicitly.
    $proxied = Invoke-Api -Path '/health' -TimeoutSec 10
    $direct = Invoke-WebRequest -Uri "$frontendUrl/api/health" -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
    $viaProxy = $direct.Content | ConvertFrom-Json
    Check 'the dev server proxies /api to the backend' ($viaProxy.status -eq 'ok') "status=$($viaProxy.status)"
} catch {
    Check 'the dev server proxies /api to the backend' $false $_.Exception.Message
}

# --------------------------------------------------------------- screenshot --

Section 'Screenshot'

if ($SkipScreenshot) {
    Note 'skipped (-SkipScreenshot).'
} else {
    $browser = @(
        (Join-Path ${env:ProgramFiles} 'Google/Chrome/Application/chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google/Chrome/Application/chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'),
        (Join-Path ${env:ProgramFiles} 'Microsoft/Edge/Application/msedge.exe')
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if (-not $browser) {
        Note 'no Chrome or Edge found; skipping the capture. The checks above do not depend on it.'
    } else {
        # Capture the *live* console, not the cold-load fixture one. The `demo`
        # hash runs the same start sequence the button does, so the frame shows
        # the run this check just produced and the values its report carries.
        # `--virtual-time-budget` gives the SPA time to resolve the demo, start
        # the run, follow it, and read the report before the frame is taken.
        $capture = @(
            '--headless=new',
            '--disable-gpu',
            '--hide-scrollbars',
            '--virtual-time-budget=25000',
            "--screenshot=$ScreenshotPath",
            '--window-size=1600,1200',
            "$frontendUrl/#console&demo"
        )
        if (Test-Path $ScreenshotPath) { Remove-Item $ScreenshotPath -Force -ErrorAction SilentlyContinue }
        # Chrome exits non-zero and writes progress to stderr even when the
        # capture succeeds, which `$ErrorActionPreference = 'Stop'` would turn
        # into a terminating error. The screenshot file is the evidence, so
        # relax the preference for the call and judge the result by the file.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $browser @capture 2>&1 | Out-Null
        } finally {
            $ErrorActionPreference = $previousPreference
        }

        $captured = Test-Path $ScreenshotPath
        Check 'the console was captured' $captured "no file at $ScreenshotPath"
        if ($captured) {
            $size = (Get-Item $ScreenshotPath).Length
            Check 'the capture is a non-trivial image' ($size -gt 2048) "size=$size bytes"
            Note "screenshot: $ScreenshotPath ($size bytes)"
        }
    }
}

# ------------------------------------------------------------------ cleanup --

Section 'Cleanup'

if ($KeepRunning) {
    Note 'stack left running (-KeepRunning).'
} elseif ($startedHere) {
    # stop-all is in start-all: it stops exactly the PIDs it recorded, and only
    # those it started itself. An adopted process (started by someone else, or
    # already running) is left alone.
    & $stackScript -BackendPort $BackendPort -FrontendPort $FrontendPort -Stop
    Start-Sleep -Milliseconds 800
    $backendDown = -not (Test-NetConnection -ComputerName '127.0.0.1' -Port $BackendPort -InformationLevel Quiet -WarningAction SilentlyContinue)
    Note "stopped the processes this check started (backend port free: $backendDown)."
} else {
    Note 'nothing was started by this check; nothing stopped.'
}

# ------------------------------------------------------------------- result --

Write-Host ''
if ($script:failures.Count -eq 0) {
    Write-Host "E2E OK - $($script:checks) checks passed." -ForegroundColor Green
    Write-Host ''
    exit 0
}

Write-Host "E2E FAILED - $($script:failures.Count) of $($script:checks) checks failed:" -ForegroundColor Red
foreach ($failure in $script:failures) {
    Write-Host "  - $failure" -ForegroundColor Red
}
Write-Host ''
exit 1

[CmdletBinding()]
param(
    [int]$TemplatePort = 8020,
    [int]$FaultyPort = 8021,
    [int]$TimeoutSeconds = 30
)

# Acceptance check for the external-SUT onboarding path.
#
# 1. Starts the template SUT from integrations/sut_template as a real process.
# 2. Runs scripts/validate-sut.ps1 against it and requires exit code 0.
# 3. Starts deliberately broken SUTs and requires validate-sut.ps1 to fail with
#    a non-zero exit code for each fault.
#
# Only the processes this script starts are stopped at the end.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$templateDir = Join-Path $repoRoot 'integrations/sut_template'
$workloadFile = Join-Path $templateDir 'workload.json'
$validateScript = Join-Path $repoRoot 'scripts/validate-sut.ps1'
$runToken = [guid]::NewGuid().ToString('N')
$workDir = Join-Path $repoRoot ".runtime/p5-onboarding-$runToken"
$null = New-Item -ItemType Directory -Path $workDir -Force

$candidates = @(
    (Join-Path $repoRoot '.venv/Scripts/python.exe'),
    (Join-Path $repoRoot '.venv/bin/python')
)
$python = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { $python = $candidate; break }
}
if (-not $python) { $python = 'python' }

$failures = [System.Collections.Generic.List[string]]::new()
$jobs = [System.Collections.Generic.List[object]]::new()

function Step([string]$name, [bool]$ok, [string]$detail = '') {
    $mark = if ($ok) { 'PASS' } else { 'FAIL' }
    $suffix = if ($detail) { " - $detail" } else { '' }
    Write-Host "  $mark  $name$suffix"
    if (-not $ok) { $failures.Add($name) }
}

function Wait-Tcp([int]$port, [int]$seconds = 30) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        $client = $null
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $client.Connect('127.0.0.1', $port)
            return $true
        } catch {
            Start-Sleep -Milliseconds 250
        } finally {
            if ($client) { $client.Dispose() }
        }
    }
    return $false
}

function Start-SutJob([string]$mode, [int]$port) {
    $job = Start-Job -ScriptBlock {
        param($root, $pythonExe, $mode, $port)
        Set-Location $root
        if ($mode) { $env:EVALPILOT_FAULTY_MODE = $mode }
        $module = if ($mode) { 'faulty_sut:app' } else { 'app:app' }
        & $pythonExe -m uvicorn $module --app-dir 'integrations/sut_template' `
            --host 127.0.0.1 --port $port --log-level warning
    } -ArgumentList $repoRoot, $python, $mode, $port
    $jobs.Add($job) | Out-Null
    if (-not (Wait-Tcp $port 45)) {
        throw "SUT process for mode '$mode' did not open port $port"
    }
    return $job
}

function Stop-SutJob($job) {
    if ($job) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Validate([int]$port, [string]$reportName) {
    $reportPath = Join-Path $workDir $reportName
    $output = & pwsh -NoProfile -File $validateScript `
        -BaseUrl "http://127.0.0.1:$port" `
        -Workload $workloadFile `
        -TimeoutSeconds $TimeoutSeconds `
        -JsonReport $reportPath 2>&1
    [System.IO.File]::WriteAllText(
        (Join-Path $workDir ($reportName -replace '\.json$', '.log')),
        ($output -join [Environment]::NewLine),
        [System.Text.UTF8Encoding]::new($false)
    )
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $output; Report = $reportPath }
}

try {
    Write-Host '-- Template SUT'
    $templateJob = Start-SutJob $null $TemplatePort
    $good = Invoke-Validate $TemplatePort 'template-report.json'
    Step 'validate-sut accepts the template SUT' ($good.ExitCode -eq 0) "exit=$($good.ExitCode)"
    if ($good.ExitCode -eq 0) {
        $goodReport = Get-Content -Raw -LiteralPath $good.Report | ConvertFrom-Json
        Step 'the template report contains no failed check' ($goodReport.checks_failed -eq 0) `
            "checks=$($goodReport.checks_total)"
        Step 'every advertised revision was exercised' (
            @($goodReport.checks | Where-Object { $_.name -like 'scenario:*@v1.0-baseline' }).Count -ge 1 -and
            @($goodReport.checks | Where-Object { $_.name -like 'scenario:*@v1.1-candidate' }).Count -ge 1
        )
        Step 'every advertised intervention was exercised' (
            @($goodReport.checks | Where-Object { $_.name -like 'intervention:*' -and $_.ok }).Count -ge 1
        )
    }
    Stop-SutJob $templateJob

    Write-Host '-- Deliberately broken SUTs'
    $faultyResults = [ordered]@{}
    foreach ($mode in @('health', 'capabilities', 'version', 'intervention', 'silent', 'response')) {
        $job = Start-SutJob $mode $FaultyPort
        $bad = Invoke-Validate $FaultyPort "faulty-$mode.json"
        $failedNames = @()
        if (Test-Path -LiteralPath $bad.Report) {
            $report = Get-Content -Raw -LiteralPath $bad.Report | ConvertFrom-Json
            $failedNames = @($report.checks | Where-Object { -not $_.ok } | ForEach-Object { $_.name })
        }
        Step "validate-sut rejects the '$mode' fault" ($bad.ExitCode -ne 0) `
            "exit=$($bad.ExitCode) failed=$($failedNames -join ',')"
        $faultyResults[$mode] = [ordered]@{
            exit_code = $bad.ExitCode
            failed_checks = $failedNames
        }
        Stop-SutJob $job
        Start-Sleep -Milliseconds 300
    }

    $summary = [ordered]@{
        status = if ($failures.Count -gt 0) { 'failed' } else { 'passed' }
        template_workload = $workloadFile
        template_exit_code = $good.ExitCode
        faulty_exit_codes = $faultyResults
        work_dir = $workDir
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $summaryPath = Join-Path $workDir 'summary.json'
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8

    if ($failures.Count -gt 0) { throw "P5 onboarding check failed: $($failures -join '; ')" }

    Write-Host "`nP5 external SUT onboarding check OK" -ForegroundColor Green
    Write-Host "Evidence: $summaryPath"
} catch {
    Write-Host "`nP5 external SUT onboarding check FAILED: $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    foreach ($job in $jobs) { Stop-SutJob $job }
}

<#
.SYNOPSIS
    Start the EvalPilot backend and frontend together, detached, and print how
    to stop them.

.DESCRIPTION
    Starts each process in its own hidden window, waits for a health gate, and
    records the PID it launched in .runtime/pids.json. The frontend gate is a
    real HTTP GET of the dev server, not a sleep: a port that is open but not
    answering renders a broken console, and a start script that returns before
    the app works is worse than one that fails.

    Three rules this script holds to:

      * No double start. If the backend health gate already answers we adopt
        the running service and start nothing; the same for the frontend. A
        second invocation is safe and does nothing destructive.
      * Track only what we launched. A PID is written only for a process this
        invocation started. An adopted process is recorded as adopted, never
        as ours, so -Stop cannot kill something it did not start.
      * Fail loudly. If a gate does not come up in time the newly started
        process is stopped again and the reason is printed, so a half-started
        stack is never left behind.

.PARAMETER BackendPort
    Backend port. Default 8000. The Vite dev proxy targets 127.0.0.1:8000, so
    changing this without changing the proxy will not work.

.PARAMETER FrontendPort
    Vite port. Default 5173.

.PARAMETER TimeoutSeconds
    How long to wait for each health gate. Default 90 (first run installs
    dependencies, which is slow).

.PARAMETER Stop
    Stop the processes this script started, using the recorded PIDs, and exit.

.PARAMETER Status
    Print what is recorded and what is actually reachable, then exit.

.PARAMETER Force
    With -Stop, also stop a recorded process whose identity check fails.

.PARAMETER SkipInstall
    Skip creating the virtualenv / installing npm packages.

.EXAMPLE
    .\scripts\start-all.ps1
    .\scripts\start-all.ps1 -Status
    .\scripts\start-all.ps1 -Stop
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$TimeoutSeconds = 90,
    [switch]$Stop,
    [switch]$Status,
    [switch]$Force,
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
$runtimeDir = Join-Path $repoRoot '.runtime'
$pidFile = Join-Path $runtimeDir 'pids.json'
$backendLog = Join-Path $runtimeDir 'backend.log'
$frontendLog = Join-Path $runtimeDir 'frontend.log'

$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"
$backendHealth = "$backendUrl/api/health"

# ---------------------------------------------------------------- helpers --

function Read-Record {
    if (-not (Test-Path $pidFile)) {
        return @{ backend = $null; frontend = $null }
    }
    try {
        $raw = Get-Content -Raw $pidFile | ConvertFrom-Json
    } catch {
        Write-Warning "Could not parse $pidFile; treating the stack as untracked."
        return @{ backend = $null; frontend = $null }
    }
    $record = @{ backend = $null; frontend = $null }
    foreach ($key in @('backend', 'frontend')) {
        $entry = $raw.$key
        if ($null -ne $entry) {
            $record[$key] = @{
                pid = [int]$entry.pid
                startedAt = [string]$entry.started_at
                command = [string]$entry.command
                adopted = [bool]$entry.adopted
            }
        }
    }
    return $record
}

function Write-Record($record) {
    if (-not (Test-Path $runtimeDir)) {
        New-Item -ItemType Directory -Path $runtimeDir | Out-Null
    }
    $payload = @{}
    foreach ($key in @('backend', 'frontend')) {
        $entry = $record[$key]
        if ($null -ne $entry) {
            $payload[$key] = @{
                pid = $entry.pid
                started_at = $entry.startedAt
                command = $entry.command
                adopted = $entry.adopted
            }
        }
    }
    $payload | ConvertTo-Json -Depth 5 | Set-Content -Path $pidFile -Encoding utf8
}

function Test-HttpOk([string]$url, [int]$timeoutSec = 3) {
    try {
        $response = Invoke-WebRequest -Uri $url -TimeoutSec $timeoutSec -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Wait-ForHttp([string]$url, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk $url) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-RecordedProcess($entry) {
    if ($null -eq $entry) { return $null }
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    # Only trust a live PID whose command line still looks like the thing we
    # started; Windows recycles PIDs and we must never kill a stranger.
    if ($entry.command) {
        $actual = (Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue).CommandLine
        if ($actual -and $actual -notlike "*$($entry.command)*") {
            Write-Warning "PID $($entry.pid) is running but its command line does not match '$($entry.command)'. Use -Force to stop it anyway."
            return $null
        }
    }
    return $process
}

<#
    Start a server detached, with its output captured to files.

    Both handles are redirected to real files rather than inherited, so the
    process - and anything it spawns in turn - writes to the log instead of
    holding this script's stdout open. A server that inherited our stdout would
    keep a caller's pipe from ever closing.

    `$token` is recorded as the process's identity. `-Stop` only trusts a live
    PID whose command line still contains it, so a recycled PID belonging to
    something else is never killed.
#>
function Start-Server($file, [string[]]$arguments, [string]$workingDirectory, [string]$stdoutLog, [string]$stderrLog, [string]$token) {
    $proc = Start-Process -FilePath $file -ArgumentList $arguments `
        -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog
    return @{ pid = $proc.Id; token = $token }
}

<#
    Record a service as adopted - without forgetting a process we started.

    A second `start-all` invocation finds the first one's processes already
    healthy and adopts them. Overwriting the record with an adopted entry would
    erase the PID the first invocation owns, and `-Stop` would then decline to
    stop a process this script did start. So an existing record for a live
    process we started is kept; adoption only fills a gap.
#>
function Set-Adopted($record, [string]$key, [string]$command) {
    $existing = $record[$key]
    if ($null -ne $existing -and -not $existing.adopted) {
        if (Get-RecordedProcess $existing) {
            Write-Host "  $key`: still PID $($existing.pid), started by an earlier run of this script." -ForegroundColor DarkGray
            return
        }
    }
    $record[$key] = @{
        pid = 0
        startedAt = (Get-Date).ToUniversalTime().ToString('o')
        command = $command
        adopted = $true
    }
}

function Stop-Recorded($entry, [string]$name, [bool]$force) {
    if ($null -eq $entry) {
        Write-Host "  $name`: nothing recorded." -ForegroundColor DarkGray
        return
    }
    if ($entry.adopted) {
        Write-Host "  $name`: adopted (PID $($entry.pid)) - not started by this script, left running." -ForegroundColor DarkGray
        return
    }
    if ($force) {
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    } else {
        $process = Get-RecordedProcess $entry
    }
    if ($null -eq $process) {
        Write-Host "  $name`: PID $($entry.pid) is not running." -ForegroundColor DarkGray
        return
    }
    # uvicorn --reload and vite both spawn children; stop the tree.
    try {
        & taskkill.exe /PID $entry.pid /T /F 2>&1 | Out-Null
    } catch {
        Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  $name`: stopped PID $($entry.pid)." -ForegroundColor Yellow
}

function Resolve-Python {
    if (Test-Path $venvPython) { return $venvPython }
    return 'python'
}

<#
    Resolve npm to an executable Start-Process can actually launch.

    On Windows `Get-Command npm` commonly resolves to `npm.ps1` - a PowerShell
    script, which Start-Process cannot execute; the launch fails and the health
    gate then reports a frontend that never came up. `npm.cmd` is the shim
    Start-Process wants, so prefer it explicitly and fall back only if it is
    genuinely absent.
#>
function Resolve-NpmCmd {
    $command = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $command) { return $null }
    if ($command.Source -and $command.Source -notlike '*.ps1') { return $command.Source }
    $cmd = Join-Path (Split-Path -Parent $command.Source) 'npm.cmd'
    if (Test-Path $cmd) { return $cmd }
    return $command.Source
}

# ------------------------------------------------------------ status / stop --

$record = Read-Record

if ($Status) {
    Write-Host ''
    Write-Host 'EvalPilot stack' -ForegroundColor Cyan
    foreach ($key in @('backend', 'frontend')) {
        $entry = $record[$key]
        $url = if ($key -eq 'backend') { $backendHealth } else { "$frontendUrl/" }
        $up = Test-HttpOk $url
        $state = if ($up) { 'reachable' } else { 'not answering' }
        if ($null -eq $entry) {
            Write-Host "  $key`: not tracked, $state" -ForegroundColor DarkGray
        } else {
            $kind = if ($entry.adopted) { 'adopted' } else { 'started here' }
            Write-Host "  $key`: PID $($entry.pid) ($kind), $state" -ForegroundColor Gray
        }
    }
    Write-Host ''
    exit 0
}

if ($Stop) {
    Write-Host ''
    Write-Host 'Stopping the EvalPilot stack' -ForegroundColor Cyan
    Stop-Recorded $record['backend'] 'backend' $Force.IsPresent
    Stop-Recorded $record['frontend'] 'frontend' $Force.IsPresent
    # Only clear entries we actually dealt with; an adopted process stays
    # recorded so -Status keeps telling the truth about it.
    if ($record['backend'] -and -not $record['backend'].adopted) { $record['backend'] = $null }
    if ($record['frontend'] -and -not $record['frontend'].adopted) { $record['frontend'] = $null }
    Write-Record $record
    Write-Host ''
    exit 0
}

# -------------------------------------------------------------------- start --

if (-not (Test-Path $backendDir)) { throw "backend directory not found at $backendDir" }
if (-not (Test-Path $frontendDir)) { throw "frontend directory not found at $frontendDir" }
if (-not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir | Out-Null }

Write-Host ''
Write-Host 'Starting the EvalPilot stack' -ForegroundColor Cyan
Write-Host ''

# --- backend ---------------------------------------------------------------

$backendEntry = $null
if (Test-HttpOk $backendHealth) {
    Write-Host "  backend: already healthy at $backendHealth - adopting, starting nothing." -ForegroundColor DarkGray
    Set-Adopted $record 'backend' 'uvicorn'
} else {
    $python = Resolve-Python
    if (-not $SkipInstall) {
        if (-not (Test-Path $venvPython)) {
            Write-Host '  backend: creating virtualenv...' -ForegroundColor Cyan
            python -m venv (Join-Path $repoRoot '.venv')
            $python = Resolve-Python
        }
        Write-Host '  backend: installing requirements...' -ForegroundColor Cyan
        & $python -m pip install --quiet --upgrade pip
        & $python -m pip install --quiet -r (Join-Path $backendDir 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw "backend dependency install failed with exit code $LASTEXITCODE" }
    }

    $env:PYTHONPATH = $backendDir
    $backendArgs = @(
        '-m', 'uvicorn', 'evalpilot.app:create_app',
        '--factory',
        '--host', '127.0.0.1',
        '--port', "$BackendPort"
    )
    $launched = Start-Server -file $python -arguments $backendArgs `
        -workingDirectory $backendDir `
        -stdoutLog $backendLog `
        -stderrLog (Join-Path $runtimeDir 'backend.err.log') `
        -token 'uvicorn'

    Write-Host "  backend: started PID $($launched.pid), waiting for $backendHealth" -ForegroundColor Gray
    if (-not (Wait-ForHttp $backendHealth $TimeoutSeconds)) {
        & taskkill.exe /PID $launched.pid /T /F 2>&1 | Out-Null
        throw "backend did not answer $backendHealth within ${TimeoutSeconds}s. See $backendLog"
    }
    Write-Host '  backend: healthy.' -ForegroundColor Green
    $record['backend'] = @{
        pid = $launched.pid
        startedAt = (Get-Date).ToUniversalTime().ToString('o')
        command = 'uvicorn'
        adopted = $false
    }
}
Write-Record $record

# --- frontend --------------------------------------------------------------

if (Test-HttpOk "$frontendUrl/") {
    Write-Host "  frontend: already answering at $frontendUrl/ - adopting, starting nothing." -ForegroundColor DarkGray
    Set-Adopted $record 'frontend' 'npm'
} else {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw 'npm was not found on PATH. Install Node.js 20 or newer and try again.'
    }
    $npmCmd = Resolve-NpmCmd
    if (-not $npmCmd) {
        throw 'Could not resolve an executable npm shim (npm.cmd). Install Node.js 20 or newer and try again.'
    }
    if (-not $SkipInstall -and -not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
        Write-Host '  frontend: installing dependencies (first run)...' -ForegroundColor Cyan
        Push-Location $frontendDir
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
        } finally {
            Pop-Location
        }
    }

    $launched = Start-Server -file $npmCmd `
        -arguments @('run', 'dev', '--', '--port', "$FrontendPort", '--strictPort') `
        -workingDirectory $frontendDir `
        -stdoutLog $frontendLog `
        -stderrLog (Join-Path $runtimeDir 'frontend.err.log') `
        -token 'npm'

    Write-Host "  frontend: started PID $($launched.pid) via $npmCmd" -ForegroundColor Gray
    if (-not (Wait-ForHttp "$frontendUrl/" $TimeoutSeconds)) {
        & taskkill.exe /PID $launched.pid /T /F 2>&1 | Out-Null
        throw "frontend did not answer $frontendUrl/ within ${TimeoutSeconds}s. See $frontendLog"
    }
    Write-Host '  frontend: answering.' -ForegroundColor Green
    $record['frontend'] = @{
        pid = $launched.pid
        startedAt = (Get-Date).ToUniversalTime().ToString('o')
        # The tracked process is the shell wrapping the npm shim; the identity
        # token must appear in *that* command line, not in the vite process the
        # shell later spawns.
        command = 'npm'
        adopted = $false
    }
}
Write-Record $record

Write-Host ''
Write-Host 'EvalPilot is up.' -ForegroundColor Green
Write-Host "  console   $frontendUrl/" -ForegroundColor Gray
Write-Host "  API       $backendUrl/api  (docs at $backendUrl/docs)" -ForegroundColor Gray
Write-Host "  PID file  $pidFile" -ForegroundColor DarkGray
Write-Host ''
Write-Host '  .\scripts\start-all.ps1 -Status   # what is running' -ForegroundColor DarkGray
Write-Host '  .\scripts\start-all.ps1 -Stop     # stop only what this script started' -ForegroundColor DarkGray
Write-Host ''

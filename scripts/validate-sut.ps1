[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = 'Base URL of the external SUT, e.g. http://127.0.0.1:8020')]
    [string]$BaseUrl,

    [string]$Workload,

    [double]$TimeoutSeconds = 20,

    [string]$Schema,

    [string]$JsonReport
)

# Validates that an external system under test can actually be evaluated:
# health, capability declaration, every advertised revision and intervention,
# every workload scenario response, and the workload's own JSON Schema.
# Exits non-zero on the first failed check set: nothing is reported as a pass
# unless it was observed over real HTTP.

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $repoRoot 'backend'

$candidates = @(
    (Join-Path $repoRoot '.venv/Scripts/python.exe'),
    (Join-Path $repoRoot '.venv/bin/python')
)
$python = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    Write-Warning 'No .venv interpreter found; falling back to the python on PATH.'
    $python = 'python'
}

$env:PYTHONPATH = $backendRoot

$arguments = @(
    '-m', 'evalpilot.sut.validator',
    '--base-url', $BaseUrl,
    '--timeout-seconds', $TimeoutSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture)
)

if ($Workload) {
    if (-not (Test-Path -LiteralPath $Workload -PathType Leaf)) {
        Write-Host "validate-sut: workload file not found: $Workload" -ForegroundColor Red
        exit 2
    }
    $arguments += @('--workload', (Resolve-Path -LiteralPath $Workload).Path)
}

if ($Schema) {
    if (-not (Test-Path -LiteralPath $Schema -PathType Leaf)) {
        Write-Host "validate-sut: schema file not found: $Schema" -ForegroundColor Red
        exit 2
    }
    $arguments += @('--schema', (Resolve-Path -LiteralPath $Schema).Path)
}

if ($JsonReport) {
    $arguments += @('--json-report', $JsonReport)
}

& $python @arguments
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) { $exitCode = 0 }
exit $exitCode

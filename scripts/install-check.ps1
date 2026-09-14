[CmdletBinding()]
param(
    [string]$ArchivePath,
    [int]$BackendPort = 8190,
    [int]$FrontendPort = 5190,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
if (-not $ArchivePath) {
    $candidate = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '..\dist') -Filter 'evalpilot-*.zip' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $candidate) { throw 'No release archive found. Run scripts/build-release.ps1 first.' }
    $ArchivePath = $candidate.FullName
}
$archive = (Resolve-Path -LiteralPath $ArchivePath).Path
$checksumFile = "$archive.sha256"
if (-not (Test-Path -LiteralPath $checksumFile -PathType Leaf)) { throw "checksum file not found: $checksumFile" }
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $repoRoot '.runtime'
$workRoot = Join-Path $runtimeRoot ("p4-install-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
$packageRoot = $null
$started = $false

function Wait-Http([string]$url, [int]$seconds = 60) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch { Start-Sleep -Milliseconds 400 }
    }
    return $false
}

try {
    $expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) { throw "release checksum mismatch: expected=$expected actual=$actual" }

    Expand-Archive -LiteralPath $archive -DestinationPath $workRoot -Force
    $packageRoot = Get-ChildItem -LiteralPath $workRoot -Directory | Select-Object -First 1 -ExpandProperty FullName
    if (-not $packageRoot) { throw 'release archive did not contain a package directory' }

    foreach ($required in @('START-HERE.md', 'RELEASE.json', 'MANIFEST.sha256', 'scripts/deploy.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $required) -PathType Leaf)) {
            throw "release is missing required file: $required"
        }
    }

    $manifestFailures = [System.Collections.Generic.List[string]]::new()
    foreach ($line in Get-Content -LiteralPath (Join-Path $packageRoot 'MANIFEST.sha256')) {
        if (-not $line.Trim()) { continue }
        $parts = $line -split '\s+', 2
        if ($parts.Count -ne 2) { $manifestFailures.Add("malformed line: $line"); continue }
        $relative = $parts[1].Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $target = Join-Path $packageRoot $relative
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { $manifestFailures.Add("missing: $relative"); continue }
        $fileHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($fileHash -ne $parts[0].ToLowerInvariant()) { $manifestFailures.Add("hash mismatch: $relative") }
    }
    if ($manifestFailures.Count -gt 0) { throw "release manifest failed: $($manifestFailures -join '; ')" }

    Write-Host '-- Start the extracted release with its own virtual environment'
    Push-Location $packageRoot
    try {
        & python scripts/deploy.py --backend-port $BackendPort --frontend-port $FrontendPort --timeout $TimeoutSeconds
        if ($LASTEXITCODE -ne 0) { throw 'scripts/deploy.py failed in the extracted release' }
        $started = $true
    } finally {
        Pop-Location
    }

    $backendHealthy = Wait-Http "http://127.0.0.1:$BackendPort/api/health" 60
    $frontendHealthy = Wait-Http "http://127.0.0.1:$FrontendPort/" 60
    if (-not $backendHealthy) { throw 'installed backend did not become healthy' }
    if (-not $frontendHealthy) { throw 'installed frontend did not become healthy' }

    Push-Location $packageRoot
    try {
        $statusOutput = (& python scripts/deploy.py --status --backend-port $BackendPort --frontend-port $FrontendPort 2>&1 | Out-String).Trim()
    } finally {
        Pop-Location
    }

    $metadata = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'RELEASE.json') | ConvertFrom-Json
    $result = [ordered]@{
        status = 'passed'
        release = $metadata.release
        commit = $metadata.commit
        archive_sha256 = $actual
        backend_url = "http://127.0.0.1:$BackendPort/api/health"
        frontend_url = "http://127.0.0.1:$FrontendPort/"
        backend_healthy = $backendHealthy
        frontend_healthy = $frontendHealthy
        status_output = $statusOutput
        installed_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $resultPath = Join-Path $repoRoot 'docs/P4_INSTALL_RESULT.json'
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding utf8
    Write-Host 'P4 release installation OK' -ForegroundColor Green
    Write-Host "Evidence: $resultPath"
} finally {
    if ($started -and $packageRoot -and (Test-Path -LiteralPath $packageRoot -PathType Container)) {
        Push-Location $packageRoot
        try { & python scripts/deploy.py --stop | Out-Null } catch { }
        Pop-Location
    }
}

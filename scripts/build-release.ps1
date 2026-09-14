[CmdletBinding()]
param(
    [string]$Version = '',
    [string]$OutputDir = 'dist'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $repoRoot '.runtime'
$distRoot = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $repoRoot $OutputDir }

if (-not $Version) {
    $Version = (git describe --tags --exact-match 2>$null)
    if (-not $Version) { $Version = (git rev-parse --short HEAD).Trim() }
}
$safeVersion = ($Version -replace '[^A-Za-z0-9._-]', '-').Trim('-')
if (-not $safeVersion) { throw 'release version resolved to an empty string' }

$token = [guid]::NewGuid().ToString('N')
$tempRoot = Join-Path $runtimeRoot "p4-release-$token"
$stage = Join-Path $tempRoot "evalpilot-$safeVersion"
$sourceArchive = Join-Path $tempRoot 'source.zip'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null

try {
    & git archive --format=zip --output=$sourceArchive HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
    Expand-Archive -LiteralPath $sourceArchive -DestinationPath $stage -Force

    $startHere = Join-Path $stage 'START-HERE.md'
    if (-not (Test-Path -LiteralPath $startHere -PathType Leaf)) {
        throw 'START-HERE.md is missing from the release source'
    }

    $commit = (git rev-parse HEAD).Trim()
    $metadata = [ordered]@{
        product = 'EvalPilot'
        release = $safeVersion
        commit = $commit
        built_at = (Get-Date).ToUniversalTime().ToString('o')
        source = 'https://github.com/zqian6263-design/EvalPilot'
        start_command = 'python scripts/deploy.py'
        verification_command = 'pwsh -NoProfile -File ./scripts/p4-mcp-retro-check.ps1'
    }
    $metadata | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage 'RELEASE.json') -Encoding utf8

    $manifestLines = Get-ChildItem -LiteralPath $stage -Recurse -File |
        Where-Object { $_.Name -ne 'MANIFEST.sha256' } |
        Sort-Object FullName |
        ForEach-Object {
            $relative = [System.IO.Path]::GetRelativePath($stage, $_.FullName).Replace('\', '/')
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            "$hash  $relative"
        }
    Set-Content -LiteralPath (Join-Path $stage 'MANIFEST.sha256') -Value $manifestLines -Encoding utf8

    $zipPath = Join-Path $distRoot "evalpilot-$safeVersion.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -LiteralPath $stage -DestinationPath $zipPath -CompressionLevel Optimal

    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumPath = "$zipPath.sha256"
    Set-Content -LiteralPath $checksumPath -Value "$zipHash  evalpilot-$safeVersion.zip" -Encoding ascii

    [pscustomobject]@{
        status = 'built'
        version = $safeVersion
        commit = $commit
        archive = $zipPath
        sha256 = $zipHash
        checksum = $checksumPath
        bytes = (Get-Item -LiteralPath $zipPath).Length
    } | ConvertTo-Json -Depth 4
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = (Resolve-Path -LiteralPath $tempRoot).Path
        $resolvedRuntime = (Resolve-Path -LiteralPath $runtimeRoot).Path
        if ($resolvedTemp.StartsWith($resolvedRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}

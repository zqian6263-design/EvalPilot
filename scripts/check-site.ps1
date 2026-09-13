[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$siteRoot = Join-Path $repoRoot 'site'
$errors = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$message) {
    $errors.Add($message)
}

$required = @(
    'index.html',
    'styles.css',
    'favicon.svg',
    'robots.txt',
    'sitemap.xml',
    '404.html'
)

foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $siteRoot $relative) -PathType Leaf)) {
        Add-Failure "Missing required file: site/$relative"
    }
}

if ($errors.Count -eq 0) {
    $indexPath = Join-Path $siteRoot 'index.html'
    $cssPath = Join-Path $siteRoot 'styles.css'
    $index = Get-Content -Raw -LiteralPath $indexPath
    $css = Get-Content -Raw -LiteralPath $cssPath

    $h1Count = [regex]::Matches($index, '<h1\b', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count
    if ($h1Count -ne 1) {
        Add-Failure "index.html must contain exactly one h1; found $h1Count"
    }

    foreach ($id in @('product', 'loop', 'evidence', 'architecture', 'start', 'demo')) {
        if ($index -notmatch ('id="' + [regex]::Escape($id) + '"')) {
            Add-Failure "Missing required section id: $id"
        }
    }

    foreach ($text in @(
        'AI 应用回归评测与自主发布质量官',
        '8 / 26',
        '52 / 0',
        '4 / 4',
        '$0.264697',
        'BLOCK / REVIEW / ALLOW',
        '不会静默回退 mock',
        'https://www.bilibili.com/video/BV1mPYY6sE1k',
        'https://github.com/zqian6263-design/EvalPilot'
    )) {
        if ($index -notlike ('*' + $text + '*')) {
            Add-Failure "Missing required content: $text"
        }
    }

    if ($index -notmatch '<html\s+lang="zh-CN"') {
        Add-Failure 'Missing zh-CN language declaration'
    }
    if ($index -notmatch '<meta\s+name="description"') {
        Add-Failure 'Missing meta description'
    }
    if ($index -notmatch 'rel="canonical"') {
        Add-Failure 'Missing canonical URL'
    }
    if ($index -notmatch 'player\.bilibili\.com/player\.html') {
        Add-Failure 'Missing Bilibili player embed'
    }
    if ($index -match '<script\b') {
        Add-Failure 'Runtime JavaScript is not allowed'
    }

    foreach ($forbidden in @('localhost', '127\.0\.0\.1', 'sk-[A-Za-z0-9]', 'ghp_[A-Za-z0-9]', 'D:\\', 'C:\\')) {
        if ($index -match $forbidden -or $css -match $forbidden) {
            Add-Failure "Forbidden pattern found: $forbidden"
        }
    }

    $hrefMatches = [regex]::Matches($index, '(?:href|src)="([^"]+)"')
    foreach ($match in $hrefMatches) {
        $target = $match.Groups[1].Value
        if ($target.StartsWith('#') -or
            $target.StartsWith('http://') -or
            $target.StartsWith('https://') -or
            $target.StartsWith('data:') -or
            $target.StartsWith('mailto:')) {
            continue
        }

        $clean = ($target -split '#')[0]
        if ([string]::IsNullOrWhiteSpace($clean) -or $clean.EndsWith('/')) {
            continue
        }

        $resolved = Join-Path $siteRoot $clean
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            Add-Failure "Broken internal asset link: $target"
        }
    }
}

if ($errors.Count -gt 0) {
    Write-Host 'Site checks failed:' -ForegroundColor Red
    $errors | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host 'Site checks passed.' -ForegroundColor Green
<#
.SYNOPSIS
    Start EvalPilot with the user-scoped DeepSeek runtime loaded.

.DESCRIPTION
    Reads the DeepSeek settings from Windows User environment variables, copies
    them into this process only, and delegates to start-all.ps1. The API key is
    never printed and never written to the repository.
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$TimeoutSeconds = 180,
    [switch]$Stop,
    [switch]$Status,
    [switch]$SkipInstall
)

$names = @(
    'EVALPILOT_LLM_API_KEY',
    'EVALPILOT_LLM_BASE_URL',
    'EVALPILOT_LLM_MODEL',
    'EVALPILOT_LLM_MODE',
    'EVALPILOT_LLM_TIMEOUT_SECONDS'
)

foreach ($name in $names) {
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $env:EVALPILOT_LLM_MODE) { $env:EVALPILOT_LLM_MODE = 'live' }
if (-not $env:EVALPILOT_LLM_BASE_URL) { $env:EVALPILOT_LLM_BASE_URL = 'https://api.deepseek.com' }
if (-not $env:EVALPILOT_LLM_MODEL) { $env:EVALPILOT_LLM_MODEL = 'deepseek-v4-pro' }
if (-not $env:EVALPILOT_LLM_TIMEOUT_SECONDS) { $env:EVALPILOT_LLM_TIMEOUT_SECONDS = '180' }

& (Join-Path $PSScriptRoot 'start-all.ps1') `
    -BackendPort $BackendPort `
    -FrontendPort $FrontendPort `
    -TimeoutSeconds $TimeoutSeconds `
    -Stop:$Stop `
    -Status:$Status `
    -SkipInstall:$SkipInstall

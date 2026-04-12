[CmdletBinding()]
param(
    [ValidateSet("None", "Pack", "Package")]
    [string]$VoiceMode = "Pack",
    [switch]$SkipOllama = $false,
    [switch]$SkipModelPull = $false,
    [switch]$SkipCompile = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PackRoot = $PSScriptRoot
$ollamaBin = "ollama"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    $ollamaBin = "ollama"
}
else {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\Ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\Ollama.exe")
    )
    $resolved = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($resolved) {
        $ollamaBin = $resolved
    }
}

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackRoot "install_python_env.ps1") -VoiceMode $VoiceMode
if ($LASTEXITCODE -ne 0) { throw "install_python_env.ps1 failed." }

if (-not $SkipOllama) {
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackRoot "install_ollama_runtime.ps1")
    if ($LASTEXITCODE -ne 0) { throw "install_ollama_runtime.ps1 failed." }
}

if (-not $SkipModelPull) {
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackRoot "pull_jarvis_models.ps1") -PullMissingOnly -OllamaBin $ollamaBin
    if ($LASTEXITCODE -ne 0) { throw "pull_jarvis_models.ps1 failed." }
}

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackRoot "verify_stack.ps1") -SkipCompile:$SkipCompile
if ($LASTEXITCODE -ne 0) { throw "verify_stack.ps1 failed." }

Write-Host "Jarvis installation pack bootstrap completed."

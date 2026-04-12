[CmdletBinding()]
param(
    [switch]$SkipCompile = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvScripts = Join-Path $RepoRoot ".venv\Scripts"
$VenvPython = Join-Path $VenvScripts "python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw ".venv not found. Run install_python_env.ps1 first."
}

$env:PATH = "$VenvScripts;$env:PATH"

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts\model_readiness.ps1") -OutputFormat json
if ($LASTEXITCODE -ne 0) {
    throw "model_readiness.ps1 failed."
}

if (-not $SkipCompile) {
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts\compile_v1.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "compile_v1.ps1 failed."
    }
}


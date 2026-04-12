[CmdletBinding()]
param(
    [ValidateSet("None", "Pack", "Package")]
    [string]$VoiceMode = "Pack",
    [switch]$ForceRecreate = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Push-Location $RepoRoot
try {
    if ($ForceRecreate -and (Test-Path -LiteralPath $VenvDir)) {
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        python -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv" }
    }

    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "requirements-dev install failed" }

    switch ($VoiceMode) {
        "Pack" {
            & $VenvPython -m pip install numpy soundfile kokoro_onnx sounddevice
            if ($LASTEXITCODE -ne 0) { throw "Kokoro pack dependency install failed" }
        }
        "Package" {
            & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements-voice.txt")
            if ($LASTEXITCODE -ne 0) { throw "requirements-voice install failed" }
        }
        default { }
    }

    Write-Host "Python environment ready: $VenvPython"
}
finally {
    Pop-Location
}


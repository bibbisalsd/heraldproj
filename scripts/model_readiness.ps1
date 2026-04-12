[CmdletBinding()]
param(
    [ValidateSet("text", "json")]
    [string]$OutputFormat = "text",
    [switch]$SkipVoice = $false,
    [switch]$RequireVoice = $false,
    [string]$OllamaBin = "ollama",
    [switch]$FailOnNotReady = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-JarvisPython {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        return $pythonCommand.Source
    }

    return "python"
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $pythonBin = Get-JarvisPython
    $env:JARVIS_MODEL_READINESS_OUTPUT = $OutputFormat
    $env:JARVIS_MODEL_READINESS_SKIP_VOICE = if ($SkipVoice) { "true" } else { "false" }
    $env:JARVIS_MODEL_READINESS_REQUIRE_VOICE = if ($RequireVoice) { "true" } else { "false" }
    $env:JARVIS_MODEL_READINESS_OLLAMA_BIN = $OllamaBin
    $env:JARVIS_MODEL_READINESS_FAIL = if ($FailOnNotReady) { "true" } else { "false" }

    $script = @"
import os
import sys

from jarvis.maintenance.model_readiness import build_readiness_report, render_readiness_report, to_json

output = os.environ.get("JARVIS_MODEL_READINESS_OUTPUT", "text").strip().lower()
skip_voice = os.environ.get("JARVIS_MODEL_READINESS_SKIP_VOICE", "false").strip().lower() == "true"
require_voice = os.environ.get("JARVIS_MODEL_READINESS_REQUIRE_VOICE", "false").strip().lower() == "true"
ollama_bin = os.environ.get("JARVIS_MODEL_READINESS_OLLAMA_BIN", "ollama").strip() or "ollama"
fail_on_not_ready = os.environ.get("JARVIS_MODEL_READINESS_FAIL", "false").strip().lower() == "true"

report = build_readiness_report(
    include_voice=not skip_voice,
    require_voice=require_voice,
    ollama_bin=ollama_bin,
)

if output == "json":
    print(to_json(report))
else:
    print(render_readiness_report(report))

if fail_on_not_ready and report.get("overall_status") != "ready":
    sys.exit(2)
"@

    $script | & $pythonBin -
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:JARVIS_MODEL_READINESS_OUTPUT -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MODEL_READINESS_SKIP_VOICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MODEL_READINESS_REQUIRE_VOICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MODEL_READINESS_OLLAMA_BIN -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MODEL_READINESS_FAIL -ErrorAction SilentlyContinue
    Pop-Location
}

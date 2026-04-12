[CmdletBinding()]
param(
    [string]$ReportDir = "./logs",
    [int]$Limit = 50,
    [int]$SinceDays = -1,
    [ValidateSet("json", "table", "text")]
    [string]$OutputFormat = "json",
    [double]$MaxRepeatFallbackRate = 0.25,
    [double]$MaxMicUnavailableRate = 0.25,
    [double]$MinVoiceSmokeCoverage = 0.50,
    [switch]$FailOnWarn,
    [switch]$FailOnCritical
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$pythonExitCode = 0

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
    $env:JARVIS_REPORT_DIR = $ReportDir
    @"
import os

from jarvis.maintenance.ops_history import evaluate_ops_health, render_ops_summary, summarize_ops_history

summary = summarize_ops_history(
    report_dir=os.environ.get("JARVIS_REPORT_DIR", "./logs"),
    limit=$Limit,
    since_days=None if $SinceDays < 0 else $SinceDays,
)
summary["health"] = evaluate_ops_health(
    summary,
    max_repeat_fallback_rate=float($MaxRepeatFallbackRate),
    max_mic_unavailable_rate=float($MaxMicUnavailableRate),
    min_voice_smoke_coverage=float($MinVoiceSmokeCoverage),
)

print(render_ops_summary(summary, output_format="$OutputFormat"))

if $FailOnCritical and summary["health"]["status"] == "critical":
    raise SystemExit(2)
if $FailOnWarn and summary["health"]["status"] in {"warn", "critical"}:
    raise SystemExit(1)
"@ | & $pythonBin -
    $pythonExitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:JARVIS_REPORT_DIR -ErrorAction SilentlyContinue
    Pop-Location
}

if ($pythonExitCode -ne 0) {
    exit $pythonExitCode
}

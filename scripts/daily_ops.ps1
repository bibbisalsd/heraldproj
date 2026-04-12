[CmdletBinding()]
param(
    [string]$InputText = "status",
    [string]$TtsBackend = "kokoro",
    [int]$MemoryRetentionDays = 90,
    [int]$VoiceMetricsRetentionDays = 14,
    [int]$KeepMemoryBackups = 5,
    [string]$MemoryDbPath = ".jarvis_memory.sqlite",
    [string]$MemoryBackupDir = "./backups",
    [string]$VoiceLogDir = "./logs",
    [string]$ReportDir = "./logs",
    [int]$OpsAlertsRetentionDays = 30,
    [int]$CrsisRetentionDays = 30,
    [switch]$NoVoiceSmoke,
    [switch]$NoVoicePersist,
    [int]$HealthSinceDays = 7,
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
    $env:JARVIS_INPUT_TEXT = $InputText
    $env:JARVIS_TTS_BACKEND_OVERRIDE = $TtsBackend
    $env:JARVIS_MEMORY_DB_PATH = $MemoryDbPath
    $env:JARVIS_MEMORY_BACKUP_DIR = $MemoryBackupDir
    $env:JARVIS_VOICE_LOG_DIR = $VoiceLogDir
    $env:JARVIS_REPORT_DIR = $ReportDir
    $env:JARVIS_NO_VOICE_SMOKE = if ($NoVoiceSmoke) { "true" } else { "false" }
    $env:JARVIS_NO_VOICE_PERSIST = if ($NoVoicePersist) { "true" } else { "false" }

    @"
import json
import os

from jarvis.maintenance.daily_ops import run_daily_ops
from jarvis.maintenance.ops_history import (
    evaluate_and_persist_crsis,
    evaluate_ops_health,
    persist_ops_alerts,
    summarize_ops_history,
)

result = run_daily_ops(
    input_text=os.environ.get("JARVIS_INPUT_TEXT", "status"),
    tts_backend=os.environ.get("JARVIS_TTS_BACKEND_OVERRIDE", "kokoro"),
    memory_db_path=os.environ.get("JARVIS_MEMORY_DB_PATH", ".jarvis_memory.sqlite"),
    memory_retention_days=$MemoryRetentionDays,
    memory_backup_dir=os.environ.get("JARVIS_MEMORY_BACKUP_DIR", "./backups"),
    memory_backup_keep=$KeepMemoryBackups,
    voice_log_dir=os.environ.get("JARVIS_VOICE_LOG_DIR", "./logs"),
    voice_metrics_retention_days=$VoiceMetricsRetentionDays,
    report_dir=os.environ.get("JARVIS_REPORT_DIR", "./logs"),
    ops_alerts_retention_days=$OpsAlertsRetentionDays,
    crsis_retention_days=$CrsisRetentionDays,
    run_voice_smoke=os.environ.get("JARVIS_NO_VOICE_SMOKE", "false").lower() != "true",
    persist_voice_payload=os.environ.get("JARVIS_NO_VOICE_PERSIST", "false").lower() != "true",
)

summary = summarize_ops_history(
    report_dir=os.environ.get("JARVIS_REPORT_DIR", "./logs"),
    limit=50,
    since_days=None if $HealthSinceDays < 0 else $HealthSinceDays,
)
health = evaluate_ops_health(
    summary,
    max_repeat_fallback_rate=float($MaxRepeatFallbackRate),
    max_mic_unavailable_rate=float($MaxMicUnavailableRate),
    min_voice_smoke_coverage=float($MinVoiceSmokeCoverage),
)
result["history_health"] = health
summary["health"] = health
result["history_alerts"] = persist_ops_alerts(
    summary,
    report_dir=os.environ.get("JARVIS_REPORT_DIR", "./logs"),
    source="daily_ops",
)
result["history_crsis"] = evaluate_and_persist_crsis(
    summary,
    report_dir=os.environ.get("JARVIS_REPORT_DIR", "./logs"),
    source="daily_ops",
)

print(json.dumps(result))

if $FailOnCritical and health["status"] == "critical":
    raise SystemExit(2)
if $FailOnWarn and health["status"] in {"warn", "critical"}:
    raise SystemExit(1)
"@ | & $pythonBin -
    $pythonExitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:JARVIS_INPUT_TEXT -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND_OVERRIDE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MEMORY_DB_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MEMORY_BACKUP_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_LOG_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_REPORT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_NO_VOICE_SMOKE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_NO_VOICE_PERSIST -ErrorAction SilentlyContinue
    Pop-Location
}

if ($pythonExitCode -ne 0) {
    exit $pythonExitCode
}

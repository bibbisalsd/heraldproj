[CmdletBinding()]
param(
    [int]$RetentionDays = 14,
    [string]$LogDir = "./logs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:JARVIS_VOICE_RETENTION_DAYS = [string]$RetentionDays
    $env:JARVIS_VOICE_LOG_DIR = $LogDir
    @"
import json
import os

from jarvis.observability.voice_metrics_export import prune_voice_metrics

result = prune_voice_metrics(
    log_dir=os.environ.get("JARVIS_VOICE_LOG_DIR", "./logs"),
    retention_days=int(os.environ.get("JARVIS_VOICE_RETENTION_DAYS", "14")),
)
print(json.dumps(result))
"@ | python -
}
finally {
    Remove-Item Env:JARVIS_VOICE_RETENTION_DAYS -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_LOG_DIR -ErrorAction SilentlyContinue
    Pop-Location
}

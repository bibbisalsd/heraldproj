[CmdletBinding()]
param(
    [int]$MemoryRetentionDays = 90,
    [int]$VoiceMetricsRetentionDays = 14,
    [int]$OpsAlertsRetentionDays = 30,
    [int]$CrsisRetentionDays = 30,
    [int]$KeepMemoryBackups = 5,
    [string]$MemoryDbPath = ".jarvis_memory.sqlite",
    [string]$MemoryBackupDir = "./backups",
    [string]$VoiceLogDir = "./logs",
    [string]$OpsReportDir = "./logs",
    [string]$CrsisLogDir = "./logs"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $env:JARVIS_MEMORY_DB_PATH = $MemoryDbPath
    $env:JARVIS_MEMORY_BACKUP_DIR = $MemoryBackupDir
    $env:JARVIS_VOICE_LOG_DIR = $VoiceLogDir
    $env:JARVIS_OPS_REPORT_DIR = $OpsReportDir
    $env:JARVIS_CRSIS_LOG_DIR = $CrsisLogDir
    @"
import json
import os
from jarvis.maintenance.retention import run_retention

result = run_retention(
    memory_db_path=os.environ.get("JARVIS_MEMORY_DB_PATH", ".jarvis_memory.sqlite"),
    memory_retention_days=$MemoryRetentionDays,
    memory_backup_dir=os.environ.get("JARVIS_MEMORY_BACKUP_DIR", "./backups"),
    memory_backup_keep=$KeepMemoryBackups,
    voice_log_dir=os.environ.get("JARVIS_VOICE_LOG_DIR", "./logs"),
    voice_metrics_retention_days=$VoiceMetricsRetentionDays,
    ops_report_dir=os.environ.get("JARVIS_OPS_REPORT_DIR", "./logs"),
    ops_alerts_retention_days=$OpsAlertsRetentionDays,
    crsis_log_dir=os.environ.get("JARVIS_CRSIS_LOG_DIR", "./logs"),
    crsis_retention_days=$CrsisRetentionDays,
)
print(json.dumps(result))
"@ | python -
}
finally {
    Remove-Item Env:JARVIS_MEMORY_DB_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_MEMORY_BACKUP_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_LOG_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_OPS_REPORT_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_CRSIS_LOG_DIR -ErrorAction SilentlyContinue
    Pop-Location
}

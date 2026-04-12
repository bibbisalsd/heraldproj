[CmdletBinding()]
param(
    [string]$TaskName = "JarvisDailyOps",
    [string]$DailyTime = "03:00",
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
    [switch]$FailOnCritical,
    [switch]$RunAsSystem,
    [switch]$Force,
    [switch]$PreviewOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Quote-Arg {
    param([string]$Value)
    return '"' + ($Value -replace '"', '\\"') + '"'
}

function Invoke-SchtasksSafe {
    param([string[]]$Args)

    $nativePref = $null
    $hasNativePref = Test-Path Variable:PSNativeCommandUseErrorActionPreference
    if ($hasNativePref) {
        $nativePref = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        & schtasks @Args | Out-Null
        return [int]$LASTEXITCODE
    }
    finally {
        if ($hasNativePref) {
            $PSNativeCommandUseErrorActionPreference = $nativePref
        }
    }
}

$dailyOpsScript = Join-Path $PSScriptRoot "daily_ops.ps1"
if (-not (Test-Path $dailyOpsScript)) {
    throw "daily_ops.ps1 not found at $dailyOpsScript"
}

$commandParts = @(
    "powershell.exe",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Quote-Arg $dailyOpsScript),
    "-InputText", (Quote-Arg $InputText),
    "-TtsBackend", (Quote-Arg $TtsBackend),
    "-MemoryRetentionDays", "$MemoryRetentionDays",
    "-VoiceMetricsRetentionDays", "$VoiceMetricsRetentionDays",
    "-KeepMemoryBackups", "$KeepMemoryBackups",
    "-MemoryDbPath", (Quote-Arg $MemoryDbPath),
    "-MemoryBackupDir", (Quote-Arg $MemoryBackupDir),
    "-VoiceLogDir", (Quote-Arg $VoiceLogDir),
    "-ReportDir", (Quote-Arg $ReportDir),
    "-OpsAlertsRetentionDays", "$OpsAlertsRetentionDays",
    "-CrsisRetentionDays", "$CrsisRetentionDays",
    "-HealthSinceDays", "$HealthSinceDays",
    "-MaxRepeatFallbackRate", "$MaxRepeatFallbackRate",
    "-MaxMicUnavailableRate", "$MaxMicUnavailableRate",
    "-MinVoiceSmokeCoverage", "$MinVoiceSmokeCoverage"
)

if ($NoVoiceSmoke) {
    $commandParts += "-NoVoiceSmoke"
}
if ($NoVoicePersist) {
    $commandParts += "-NoVoicePersist"
}
if ($FailOnWarn) {
    $commandParts += "-FailOnWarn"
}
if ($FailOnCritical) {
    $commandParts += "-FailOnCritical"
}

$taskCommand = $commandParts -join " "

$exists = $false
$queryExit = Invoke-SchtasksSafe @("/Query", "/TN", $TaskName)
if ($queryExit -eq 0) {
    $exists = $true
}

$createArgs = @("/Create", "/SC", "DAILY", "/TN", $TaskName, "/TR", $taskCommand, "/ST", $DailyTime)
if ($RunAsSystem) {
    $createArgs += @("/RU", "SYSTEM", "/RL", "HIGHEST")
}
if ($Force -or $exists) {
    $createArgs += "/F"
}

if ($PreviewOnly) {
    @{
        preview_only = $true
        task_name = $TaskName
        exists = $exists
        daily_time = $DailyTime
        run_as_system = [bool]$RunAsSystem
        command = $taskCommand
        create_args = $createArgs
    } | ConvertTo-Json -Depth 6
    exit 0
}

if ($exists -and -not $Force) {
    throw "Task '$TaskName' already exists. Use -Force to replace it."
}

$createExitCode = Invoke-SchtasksSafe $createArgs
if ($createExitCode -ne 0) {
    throw "Failed to create/update scheduled task '$TaskName'."
}

@{
    created = $true
    task_name = $TaskName
    daily_time = $DailyTime
    run_as_system = [bool]$RunAsSystem
    command = $taskCommand
} | ConvertTo-Json -Depth 4

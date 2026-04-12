[CmdletBinding()]
param(
    [switch]$SkipCompile = $false,
    [switch]$SkipVoiceText = $false,
    [switch]$SkipVoiceMic = $true,
    [switch]$RunVoiceMic,
    [double]$MicDurationSeconds = 3.0,
    [int]$SampleRate = 16000,
    [string]$InputDevice = "",
    [string]$OutputDevice = "",
    [string]$ArtifactPath = "./artifacts/target_acceptance_report.json",
    [string]$OllamaBin = "ollama"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($RunVoiceMic) {
    $SkipVoiceMic = $false
}

function Invoke-ScriptCapture {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    return @{
        exit_code = $exitCode
        lines = @($output | ForEach-Object { "$_" })
        text = ((@($output | ForEach-Object { "$_" }) -join "`n").Trim())
    }
}

function Convert-JsonSafe {
    param(
        [string]$Text
    )

    $trimmed = ($Text | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        return $null
    }
    try {
        return (ConvertFrom-Json -InputObject $trimmed)
    }
    catch {
        return $null
    }
}

function Get-VoiceAssessment {
    param(
        [object]$Payload
    )

    if ($null -eq $Payload) {
        return [ordered]@{
            capture_status = "unknown"
            transcribe_status = "unknown"
            playback_status = "unknown"
            reason = "payload_missing"
        }
    }

    $reason = ""
    if ($null -ne $Payload.fallback_reason -and -not [string]::IsNullOrWhiteSpace([string]$Payload.fallback_reason)) {
        $reason = [string]$Payload.fallback_reason
    }
    elseif ($null -ne $Payload.reason -and -not [string]::IsNullOrWhiteSpace([string]$Payload.reason)) {
        $reason = [string]$Payload.reason
    }

    $captureStatus = if ($Payload.audio_capture_ok -eq $true) {
        "pass"
    }
    elseif ($Payload.audio_capture_ok -eq $false) {
        "fail"
    }
    else {
        "unknown"
    }

    $transcribeStatus = if ($Payload.transcribe_ok -eq $true) {
        "pass"
    }
    elseif ($Payload.audio_capture_ok -eq $true) {
        "warn"
    }
    elseif ($reason -like "input_device*" -or $reason -like "output_device*") {
        "not_run"
    }
    else {
        "fail"
    }

    $playbackStatus = if ($reason -like "input_device*" -or $reason -like "output_device*") {
        "not_run"
    }
    elseif ([string]$Payload.tts_backend -eq "kokoro" -and [string]::IsNullOrWhiteSpace([string]$Payload.tts_error)) {
        "pass"
    }
    elseif ([string]::IsNullOrWhiteSpace([string]$Payload.tts_backend)) {
        "unknown"
    }
    else {
        "warn"
    }

    return [ordered]@{
        capture_status = $captureStatus
        transcribe_status = $transcribeStatus
        playback_status = $playbackStatus
        reason = $reason
    }
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $report = [ordered]@{
        checked_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        voice_settings = [ordered]@{
            expected_spoken_phrase = "Jarvis status check April second"
            mic_duration_seconds = $MicDurationSeconds
            sample_rate = $SampleRate
            input_device = $InputDevice
            output_device = $OutputDevice
        }
        readiness = $null
        compile = $null
        voice_text = $null
        voice_mic = $null
        overall_status = "pass"
    }

    $readiness = Invoke-ScriptCapture -FilePath (Join-Path $PSScriptRoot "model_readiness.ps1") -Arguments @("-OutputFormat", "json", "-OllamaBin", $OllamaBin)
    $readinessPayload = Convert-JsonSafe -Text ([string]$readiness.text)
    $report.readiness = @{
        exit_code = $readiness.exit_code
        payload = $readinessPayload
        raw = $readiness.text
    }
    if ($readiness.exit_code -ne 0 -or $null -eq $readinessPayload -or $readinessPayload.overall_status -ne "ready") {
        $report.overall_status = "warn"
    }

    if (-not $SkipCompile) {
        $compile = Invoke-ScriptCapture -FilePath (Join-Path $PSScriptRoot "compile_v1.ps1") -Arguments @("-SkipModelPull")
        $report.compile = @{
            exit_code = $compile.exit_code
            raw = $compile.text
        }
        if ($compile.exit_code -ne 0) {
            $report.overall_status = "warn"
        }
    }

    if (-not $SkipVoiceText) {
        $voiceText = Invoke-ScriptCapture -FilePath (Join-Path $PSScriptRoot "voice_smoke.ps1") -Arguments @("-InputText", "status", "-TtsBackend", "kokoro", "-NoPersist")
        $voiceTextPayload = Convert-JsonSafe -Text ([string]$voiceText.text)
        $report.voice_text = @{
            exit_code = $voiceText.exit_code
            payload = $voiceTextPayload
            raw = $voiceText.text
        }
        if (
            $voiceText.exit_code -ne 0 -or
            $null -eq $voiceTextPayload -or
            $voiceTextPayload.ok -ne $true -or
            [string]$voiceTextPayload.tts_backend -ne "kokoro"
        ) {
            $report.overall_status = "warn"
        }
    }

    if (-not $SkipVoiceMic) {
        $voiceMicArgs = @(
            "-FromMic",
            "-DurationSeconds", ([string]$MicDurationSeconds),
            "-SampleRate", ([string]$SampleRate),
            "-TtsBackend", "kokoro",
            "-NoPersist"
        )
        if (-not [string]::IsNullOrWhiteSpace($InputDevice)) {
            $voiceMicArgs += @("-InputDevice", $InputDevice)
        }
        if (-not [string]::IsNullOrWhiteSpace($OutputDevice)) {
            $voiceMicArgs += @("-OutputDevice", $OutputDevice)
        }

        $voiceMic = Invoke-ScriptCapture -FilePath (Join-Path $PSScriptRoot "voice_smoke.ps1") -Arguments $voiceMicArgs
        $voiceMicPayload = Convert-JsonSafe -Text ([string]$voiceMic.text)
        $report.voice_mic = @{
            exit_code = $voiceMic.exit_code
            payload = $voiceMicPayload
            assessment = Get-VoiceAssessment -Payload $voiceMicPayload
            raw = $voiceMic.text
        }
        if (
            $voiceMic.exit_code -ne 0 -or
            $null -eq $voiceMicPayload -or
            $voiceMicPayload.ok -ne $true -or
            $voiceMicPayload.transcribe_ok -ne $true -or
            [string]$voiceMicPayload.tts_backend -ne "kokoro" -or
            -not [string]::IsNullOrWhiteSpace([string]$voiceMicPayload.fallback_reason)
        ) {
            $report.overall_status = "warn"
        }
    }

    $artifactFullPath = Join-Path (Get-Location) ($ArtifactPath -replace '^[.][\\/]', '')
    $artifactDir = Split-Path -Parent $artifactFullPath
    if (-not (Test-Path -LiteralPath $artifactDir)) {
        New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
    }
    ($report | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $artifactFullPath -Encoding UTF8
    Write-Output ($report | ConvertTo-Json -Depth 10)
}
finally {
    Pop-Location
}

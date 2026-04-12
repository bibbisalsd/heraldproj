[CmdletBinding()]
param(
    [string]$InputText = "status",
    [switch]$FromMic,
    [double]$DurationSeconds = 3.0,
    [int]$SampleRate = 16000,
    [string]$InputDevice = "",
    [string]$OutputDevice = "",
    [string]$TtsBackend = "kokoro",
    [string]$ExpectBackend = "",
    [string]$LogDir = "./logs",
    [switch]$NoPersist
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
    $defaultPackDir = Join-Path (Split-Path -Parent $PSScriptRoot) "jarvis\\voice\\kokoro_pack"
    if (Test-Path (Join-Path $defaultPackDir "jarvis_launcher.py")) {
        $env:JARVIS_USE_KOKORO_PACK = "true"
        $env:JARVIS_KOKORO_PACK_DIR = $defaultPackDir
        $defaultPackPython = Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\\Scripts\\python.exe"
        if (Test-Path $defaultPackPython) {
            $env:JARVIS_KOKORO_PYTHON = $defaultPackPython
        }
    }

    $env:JARVIS_VOICE_INPUT = $InputText
    $env:JARVIS_VOICE_FROM_MIC = if ($FromMic) { "true" } else { "false" }
    $env:JARVIS_VOICE_DURATION = [string]$DurationSeconds
    $env:JARVIS_VOICE_SAMPLE_RATE = [string]$SampleRate
    $env:JARVIS_VOICE_INPUT_DEVICE = $InputDevice
    $env:JARVIS_VOICE_OUTPUT_DEVICE = $OutputDevice
    $env:JARVIS_TTS_BACKEND = $TtsBackend
    $env:JARVIS_EXPECT_BACKEND = $ExpectBackend
    $env:JARVIS_VOICE_LOG_DIR = $LogDir
    $env:JARVIS_VOICE_NO_PERSIST = if ($NoPersist) { "true" } else { "false" }

    $pythonOutput = @"
import json
import os

from jarvis.observability.voice_metrics_export import persist_voice_metrics
from jarvis.voice.runtime import VoiceRuntime

def _env_device(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw

rt = VoiceRuntime()
if os.environ.get("JARVIS_VOICE_FROM_MIC", "false").lower() == "true":
    duration = float(os.environ.get("JARVIS_VOICE_DURATION", "3.0"))
    sample_rate = int(os.environ.get("JARVIS_VOICE_SAMPLE_RATE", "16000"))
    input_device = _env_device("JARVIS_VOICE_INPUT_DEVICE")
    output_device = _env_device("JARVIS_VOICE_OUTPUT_DEVICE")
    res = rt.process_microphone(
        duration_seconds=duration,
        sample_rate=sample_rate,
        input_device=input_device,
        output_device=output_device,
    )
else:
    text = os.environ.get("JARVIS_VOICE_INPUT", "status")
    res = rt.process_audio(text.encode("utf-8"))

payload = {
    **res.to_payload(),
    "tts_backend": rt.tts.last_backend,
    "tts_error": rt.tts.last_error,
    "stt_model": rt.stt.model_name,
    "stt_error": rt.stt.last_error,
    "voice_metrics": rt.metrics_snapshot(),
}

if os.environ.get("JARVIS_VOICE_NO_PERSIST", "false").lower() != "true":
    payload["persisted_files"] = persist_voice_metrics(
        payload,
        log_dir=os.environ.get("JARVIS_VOICE_LOG_DIR", "./logs"),
    )

expect = os.environ.get("JARVIS_EXPECT_BACKEND", "").strip().lower()
if expect and payload["tts_backend"] != expect:
    print(json.dumps(payload))
    raise SystemExit(f"expected_backend_mismatch: expected={expect} actual={payload['tts_backend']}")

print(json.dumps(payload))
"@ | & $pythonBin - 2>&1
    $pythonExitCode = $LASTEXITCODE

    foreach ($line in @($pythonOutput)) {
        Write-Output $line
    }

    if ($pythonExitCode -ne 0) {
        $lastLine = ""
        if (@($pythonOutput).Count -gt 0) {
            $lastLine = [string]@($pythonOutput)[-1]
        }
        if ([string]::IsNullOrWhiteSpace($lastLine)) {
            throw "voice_smoke_failed (python_exit_code=$pythonExitCode)"
        }
        throw "voice_smoke_failed (python_exit_code=$pythonExitCode): $lastLine"
    }
}
finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_INPUT -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_FROM_MIC -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_DURATION -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_SAMPLE_RATE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_INPUT_DEVICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_OUTPUT_DEVICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_EXPECT_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_LOG_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_NO_PERSIST -ErrorAction SilentlyContinue
    Pop-Location
}

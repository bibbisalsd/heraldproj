[CmdletBinding()]
param(
    [string]$InputText = "status",
    [switch]$FromMic,
    [double]$DurationSeconds = 3.0,
    [int]$SampleRate = 16000,
    [string]$InputDevice = "",
    [string]$OutputDevice = "",
    [switch]$SaveDevices,
    [switch]$ListDevices,
    [switch]$ShowConfig,
    [switch]$Diagnostics,
    [string]$LogDir = "./logs"
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

    $env:JARVIS_TTS_BACKEND = "kokoro"
    $env:JARVIS_VOICE_INPUT = $InputText
    $env:JARVIS_VOICE_FROM_MIC = if ($FromMic) { "true" } else { "false" }
    $env:JARVIS_VOICE_DURATION = [string]$DurationSeconds
    $env:JARVIS_VOICE_SAMPLE_RATE = [string]$SampleRate
    $env:JARVIS_VOICE_INPUT_DEVICE = $InputDevice
    $env:JARVIS_VOICE_OUTPUT_DEVICE = $OutputDevice

    # Handle ListDevices switch
    if ($ListDevices) {
        $env:JARVIS_VOICE_CMD = "list_devices"
    } elseif ($ShowConfig) {
        $env:JARVIS_VOICE_CMD = "show_config"
    } elseif ($SaveDevices) {
        $env:JARVIS_VOICE_CMD = "save_devices"
    } elseif ($Diagnostics) {
        $env:JARVIS_VOICE_CMD = "diagnostics"
        $env:JARVIS_VOICE_LOG_DIR = $LogDir
    } else {
        $env:JARVIS_VOICE_CMD = "run"
    }

    @"
import json
import os
from jarvis.voice.runtime import VoiceRuntime
from jarvis.voice import audio_device
from jarvis.voice.diagnostics import VoiceDiagnostics

def _env_device(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw

cmd = os.environ.get("JARVIS_VOICE_CMD", "run")
log_dir = os.environ.get("JARVIS_VOICE_LOG_DIR", "./logs")

if cmd == "list_devices":
    summary = audio_device.get_device_summary()
    print(json.dumps(summary, indent=2))
elif cmd == "show_config":
    config = audio_device.load_saved_device_config()
    summary = audio_device.get_device_summary()
    print(json.dumps({
        "saved_config": config,
        "available_input_devices": summary["input_devices"],
        "available_output_devices": summary["output_devices"],
        "default_input": summary["default_input"],
        "default_output": summary["default_output"],
    }, indent=2))
elif cmd == "save_devices":
    rt = VoiceRuntime()
    input_dev = _env_device("JARVIS_VOICE_INPUT_DEVICE")
    output_dev = _env_device("JARVIS_VOICE_OUTPUT_DEVICE")
    ok = rt.save_device_preferences(input_device=input_dev, output_device=output_dev)
    config = audio_device.load_saved_device_config()
    print(json.dumps({
        "ok": ok,
        "saved_config": config,
    }, indent=2))
elif cmd == "diagnostics":
    diag = VoiceDiagnostics(log_dir=log_dir)
    input_dev = _env_device("JARVIS_VOICE_INPUT_DEVICE")
    output_dev = _env_device("JARVIS_VOICE_OUTPUT_DEVICE")
    result = diag.collect(
        input_device=input_dev,
        output_device=output_dev,
        sample_rate=int(os.environ.get("JARVIS_VOICE_SAMPLE_RATE", "16000")),
        duration_seconds=float(os.environ.get("JARVIS_VOICE_DURATION", "3.0")),
        test_text=os.environ.get("JARVIS_VOICE_INPUT", "status"),
    )
    filepath = diag.save_diagnostics(result)
    output = result.to_dict()
    output["saved_to"] = filepath
    print(json.dumps(output, indent=2))
else:
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
        res = rt.process_audio(os.environ.get("JARVIS_VOICE_INPUT", "status").encode("utf-8"))
    print(json.dumps({
        **res.to_payload(),
        "tts_backend": rt.tts.last_backend,
        "tts_error": rt.tts.last_error,
        "stt_model": rt.stt.model_name,
        "stt_error": rt.stt.last_error,
    }))
"@ | & $pythonBin -
}
finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_INPUT -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_FROM_MIC -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_DURATION -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_SAMPLE_RATE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_INPUT_DEVICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_OUTPUT_DEVICE -ErrorAction SilentlyContinue
    Pop-Location
}

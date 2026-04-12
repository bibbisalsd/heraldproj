[CmdletBinding()]
param(
    [double]$DurationSeconds = 6.0,
    [int]$SampleRate = 16000,
    [string]$InputDevice = "1",
    [string]$OutputDevice = "6",
    [string]$InputText = "",
    [int]$MaxTurns = 0,
    [double]$PauseSeconds = 0.9,
    [double]$MaxUtteranceSeconds = 18.0
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
    $env:JARVIS_VOICE_DURATION = [string]$DurationSeconds
    $env:JARVIS_VOICE_SAMPLE_RATE = [string]$SampleRate
    $env:JARVIS_VOICE_INPUT_DEVICE = $InputDevice
    $env:JARVIS_VOICE_OUTPUT_DEVICE = $OutputDevice
    $env:JARVIS_VOICE_INPUT_TEXT = $InputText
    $env:JARVIS_VOICE_MAX_TURNS = [string]$MaxTurns
    $env:JARVIS_VOICE_PAUSE_SECONDS = [string]$PauseSeconds
    $env:JARVIS_VOICE_MAX_UTTERANCE_SECONDS = [string]$MaxUtteranceSeconds

    @"
import os
import time
from jarvis.voice.runtime import VoiceRuntime


def _env_device(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


duration = float(os.environ.get("JARVIS_VOICE_DURATION", "6.0"))
sample_rate = int(os.environ.get("JARVIS_VOICE_SAMPLE_RATE", "16000"))
input_device = _env_device("JARVIS_VOICE_INPUT_DEVICE")
output_device = _env_device("JARVIS_VOICE_OUTPUT_DEVICE")
input_text = os.environ.get("JARVIS_VOICE_INPUT_TEXT", "").strip()
max_turns = int(os.environ.get("JARVIS_VOICE_MAX_TURNS", "0") or "0")
pause_seconds = float(os.environ.get("JARVIS_VOICE_PAUSE_SECONDS", "0.9"))
max_utterance_seconds = float(os.environ.get("JARVIS_VOICE_MAX_UTTERANCE_SECONDS", "18.0"))

rt = VoiceRuntime()
greeting = ""
if not input_text:
    greeting = rt.launch_greeting(speak=True)

print("Jarvis voice mode started.", flush=True)
print("Press Ctrl+C to stop.", flush=True)
print("Wait for 'Listening now...' before you speak.", flush=True)
print("Say 'Jarvis' anywhere in your sentence when you want a reply.", flush=True)
print("After I reply, you can continue speaking for a short time without repeating Jarvis.", flush=True)
if greeting:
    print(f"Jarvis> {greeting}", flush=True)
if input_text:
    print(f"Fixed input text: {input_text}", flush=True)
else:
    print(f"Listening continuously at {sample_rate} Hz.", flush=True)
    print(f"Speech pause threshold: {pause_seconds:g}s. Max utterance: {max_utterance_seconds:g}s.", flush=True)
    if input_device is not None:
        print(f"Input device: {input_device}", flush=True)
    if output_device is not None:
        print(f"Output device audit target: {output_device}", flush=True)

turn = 0
try:
    while True:
        if max_turns > 0 and turn >= max_turns:
            break

        turn += 1
        print("", flush=True)
        if input_text:
            print(f"[Turn {turn}] Processing input text...", flush=True)
            result = rt.process_audio(input_text.encode("utf-8"))
        else:
            print(f"[Turn {turn}] Listening now...", flush=True)
            result = rt.process_microphone_passive(
                duration_seconds=duration,
                sample_rate=sample_rate,
                input_device=input_device,
                output_device=output_device,
                require_wake_word=True,
                continuous=True,
                pause_seconds=pause_seconds,
                max_duration_seconds=max_utterance_seconds,
            )

        heard = result.transcribed_text.strip()
        if result.reason == "ignored_no_speech":
            continue
        if result.reason == "wake_word_not_detected":
            print(f"You> {heard}", flush=True)
            print("Jarvis> [ignored: wake word not detected]", flush=True)
            continue

        print(f"You> {heard or '[no speech recognized]'}", flush=True)
        if result.text:
            print(f"Jarvis> {result.text}", flush=True)
        if rt.stt.last_error:
            print(f"STT error> {rt.stt.last_error}", flush=True)

        if input_text:
            break

        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nStopping Jarvis.", flush=True)
finally:
    try:
        rt.shutdown()
    except Exception:
        pass
"@ | & $pythonBin -
}
finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_DURATION -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_SAMPLE_RATE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_INPUT_DEVICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_OUTPUT_DEVICE -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_INPUT_TEXT -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_MAX_TURNS -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_PAUSE_SECONDS -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_VOICE_MAX_UTTERANCE_SECONDS -ErrorAction SilentlyContinue
    Pop-Location
}

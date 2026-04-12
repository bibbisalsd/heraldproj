"""Jarvis voice loop for Linux — mic input + TTS output."""
import os
import time

os.environ.setdefault("JARVIS_USE_KOKORO_PACK", "true")
os.environ.setdefault("JARVIS_KOKORO_PACK_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "jarvis", "voice", "kokoro_pack"))
os.environ.setdefault("JARVIS_TTS_BACKEND", "kokoro")

from jarvis.voice.runtime import VoiceRuntime

def _env_device(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw

DURATION = float(os.environ.get("JARVIS_VOICE_DURATION", "6.0"))
SAMPLE_RATE = int(os.environ.get("JARVIS_VOICE_SAMPLE_RATE", "16000"))
PAUSE_SECONDS = float(os.environ.get("JARVIS_VOICE_PAUSE_SECONDS", "2.0"))
MAX_UTTERANCE = float(os.environ.get("JARVIS_VOICE_MAX_UTTERANCE_SECONDS", "18.0"))
INPUT_DEVICE = _env_device("JARVIS_VOICE_INPUT_DEVICE")
OUTPUT_DEVICE = _env_device("JARVIS_VOICE_OUTPUT_DEVICE")

rt = VoiceRuntime()

# Calibrate microphone for ambient noise floor
calibration = rt.calibrate_microphone(duration_seconds=2.0, input_device=INPUT_DEVICE)
SPEECH_THRESHOLD = calibration.get("speech_threshold")
SILENCE_THRESHOLD = calibration.get("silence_threshold")

greeting = rt.launch_greeting(speak=True)
print("Jarvis voice mode started.", flush=True)
print("Press Ctrl+C to stop.", flush=True)
print("Wait for 'Listening now...' before you speak.", flush=True)
print('Say "Jarvis" anywhere in your sentence when you want a reply.', flush=True)
if greeting:
    print(f"Jarvis> {greeting}", flush=True)

print(f"Listening at {SAMPLE_RATE} Hz. Pause: {PAUSE_SECONDS}s. Max utterance: {MAX_UTTERANCE}s.", flush=True)
if INPUT_DEVICE is not None:
    print(f"Input device: {INPUT_DEVICE}", flush=True)
if OUTPUT_DEVICE is not None:
    print(f"Output device: {OUTPUT_DEVICE}", flush=True)

turn = 0
try:
    while True:
        turn += 1
        print(f"\n[Turn {turn}] Listening now...", flush=True)
        result = rt.process_microphone_passive(
            duration_seconds=DURATION,
            sample_rate=SAMPLE_RATE,
            input_device=INPUT_DEVICE,
            output_device=OUTPUT_DEVICE,
            require_wake_word=True,
            continuous=True,
            pause_seconds=PAUSE_SECONDS,
            max_duration_seconds=MAX_UTTERANCE,
            speech_threshold=SPEECH_THRESHOLD,
            silence_threshold=SILENCE_THRESHOLD,
        )

        heard = result.transcribed_text.strip()
        if result.reason == "ignored_no_speech":
            continue

        # If we captured audio but couldn't transcribe it, prompt user to speak louder
        if result.audio_capture_ok and not result.transcribe_ok and not heard:
            print("  [mic] Captured audio but transcription was empty.", flush=True)
            rt.tts.speak("I heard something, but I couldn't make out the words. Could you speak a bit louder?")
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

        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nStopping Jarvis.", flush=True)
finally:
    try:
        rt.shutdown()
    except Exception:
        pass

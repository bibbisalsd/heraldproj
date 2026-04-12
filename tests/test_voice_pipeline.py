from __future__ import annotations
from jarvis.voice.runtime import VoiceRuntime


def test_voice_pipeline_local_mic_to_tts():
    runtime = VoiceRuntime()
    result = runtime.process_audio(b"status")
    assert result.lane == "realtime"
    assert "online" in runtime.tts.last_spoken.lower()

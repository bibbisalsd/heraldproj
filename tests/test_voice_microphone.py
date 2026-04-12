from __future__ import annotations

import queue

from jarvis.voice.runtime import VoiceRuntime
from jarvis.voice.stt import STT


def _mock_devices() -> list[dict[str, object]]:
    return [
        {
            "index": 1,
            "name": "Default Mic",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "default_samplerate": 44100,
            "is_default_input": True,
            "is_default_output": False,
        },
        {
            "index": 6,
            "name": "Default Speakers",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 44100,
            "is_default_input": False,
            "is_default_output": True,
        },
    ]


def test_stt_text_payload_still_shortcuts() -> None:
    stt = STT()
    assert stt.transcribe(b"status") == "status"


def test_stt_default_model_name_is_valid_faster_whisper_alias() -> None:
    stt = STT()
    assert stt.model_name == "small.en"


def test_stt_binary_payload_not_treated_as_text_when_whisper_missing(monkeypatch) -> None:
    stt = STT()
    monkeypatch.setattr(stt, "_is_whisper_available", lambda: False)

    wav_like = b"RIFF\x00\x10\x00\x00WAVEfmt \x10\x00\x00\x00"
    assert stt.transcribe(wav_like) == ""


def test_voice_runtime_process_microphone_unavailable_fallback() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b""

    result = runtime.process_microphone(duration_seconds=0.1)
    assert result.lane == "realtime"
    assert "microphone capture unavailable" in result.text.lower()
    assert result.reason == "mic_unavailable"
    assert result.selected_input_device["index"] == 1
    assert result.selected_output_device["index"] == 6


def test_voice_runtime_process_microphone_with_audio() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"status"

    result = runtime.process_microphone(duration_seconds=0.1)
    assert result.lane == "realtime"
    assert "online" in runtime.tts.last_spoken.lower()
    assert result.transcribed_text == "status"
    assert result.selected_input_device["name"] == "Default Mic"
    assert result.selected_output_device["name"] == "Default Speakers"


def test_voice_runtime_passive_microphone_ignores_silence_without_speaking(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "")
    def mock_speak_reliable(text: str, **kwargs):
        runtime.tts.last_spoken = text
        return {"ok": "true"}
    monkeypatch.setattr(runtime.tts, "speak_reliable", mock_speak_reliable)

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == "ignored_no_speech"
    assert result.text == ""
    assert result.transcribed_text == ""


def test_voice_runtime_passive_microphone_ignores_punctuation_only_transcript(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "...")
    def mock_speak_reliable(text: str, **kwargs):
        runtime.tts.last_spoken = text
        return {"ok": "true"}
    monkeypatch.setattr(runtime.tts, "speak_reliable", mock_speak_reliable)

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == "ignored_no_speech"
    assert result.text == ""
    assert result.transcribed_text == ""


def test_voice_runtime_passive_microphone_requires_wake_word(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "what time is it")
    def mock_speak_reliable(text: str, **kwargs):
        runtime.tts.last_spoken = text
        return {"ok": "true"}
    monkeypatch.setattr(runtime.tts, "speak_reliable", mock_speak_reliable)

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == "wake_word_not_detected"
    assert result.text == ""
    assert result.transcribed_text == "what time is it"


def test_voice_runtime_passive_microphone_accepts_wake_word_inside_sentence(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "can you help me jarvis")
    monkeypatch.setattr(
        runtime.core_runtime,
        "run_turn",
        lambda _text, source="local_mic": {"lane": "realtime", "text": "I can help.", "source": source},
    )

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == ""
    assert result.text == "I can help."
    assert result.transcribed_text == "can you help me jarvis"


def test_voice_runtime_passive_microphone_accepts_wake_word_near_miss(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "javis what can you do")
    monkeypatch.setattr(
        runtime.core_runtime,
        "run_turn",
        lambda _text, source="local_mic": {"lane": "realtime", "text": "I can help.", "source": source},
    )

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == ""
    assert result.text == "I can help."
    assert result.transcribed_text == "javis what can you do"


def test_voice_runtime_passive_microphone_allows_onboarding_follow_up_without_wake_word(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    runtime.launch_greeting(speak=False)
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "James")
    monkeypatch.setattr(
        runtime.core_runtime,
        "run_turn",
        lambda _text, source="local_mic": {
            "lane": "realtime",
            "text": "Thank you. I will remember your name as James.",
            "source": source,
            "sensitive_input": False,
        },
    )

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == ""
    assert "remember your name as James" in result.text
    assert result.transcribed_text == "James"


def test_voice_runtime_passive_microphone_allows_follow_up_without_wake_word_after_recent_turn(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    runtime.core_runtime.conversation.activate_follow_up_window()
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "what's your status")
    monkeypatch.setattr(
        runtime.core_runtime,
        "run_turn",
        lambda _text, source="local_mic": {
            "lane": "realtime",
            "text": "I am online and ready.",
            "source": source,
            "sensitive_input": False,
        },
    )

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == ""
    assert "online" in result.text.lower()
    assert result.transcribed_text == "what's your status"


def test_voice_runtime_passive_microphone_ignores_unrelated_follow_up_without_wake_word(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    runtime.core_runtime.conversation.activate_follow_up_window()
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "They what?")
    def mock_speak_reliable(text: str, **kwargs):
        runtime.tts.last_spoken = text
        return {"ok": "true"}
    monkeypatch.setattr(runtime.tts, "speak_reliable", mock_speak_reliable)

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == "wake_word_not_detected"
    assert result.text == ""
    assert result.transcribed_text == "They what?"


def test_voice_runtime_passive_microphone_can_use_continuous_capture(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone_until_pause = lambda **_kwargs: b"audio"
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "jarvis status")
    monkeypatch.setattr(
        runtime.core_runtime,
        "run_turn",
        lambda _text, source="local_mic": {
            "lane": "realtime",
            "text": "I am currently online.",
            "source": source,
            "sensitive_input": False,
        },
    )

    result = runtime.process_microphone_passive(duration_seconds=0.1, continuous=True)

    assert result.reason == ""
    assert "online" in result.text.lower()
    assert result.transcribed_text == "jarvis status"


def test_voice_runtime_passive_microphone_continuous_allows_onboarding_reply(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone_until_pause = lambda **_kwargs: b"audio"
    runtime.launch_greeting(speak=False)
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "my name is james")
    monkeypatch.setattr(
        runtime.core_runtime,
        "run_turn",
        lambda _text, source="local_mic": {
            "lane": "realtime",
            "text": "Thank you. I will remember your name as James.",
            "source": source,
            "sensitive_input": False,
        },
    )

    result = runtime.process_microphone_passive(duration_seconds=0.1, continuous=True)

    assert result.reason == ""
    assert "remember your name as James" in result.text
    assert result.transcribed_text == "my name is james"


def test_voice_runtime_passive_microphone_continuous_timeout_is_ignored_no_speech(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]

    def _timeout_capture(**_kwargs):
        runtime._last_capture_reason = "no_speech_timeout"
        return b""

    runtime.capture_microphone_until_pause = _timeout_capture
    def mock_speak_reliable(text: str, **kwargs):
        runtime.tts.last_spoken = text
        return {"ok": "true"}
    monkeypatch.setattr(runtime.tts, "speak_reliable", mock_speak_reliable)

    result = runtime.process_microphone_passive(duration_seconds=0.1, continuous=True)

    assert result.reason == "ignored_no_speech"
    assert result.text == ""
    assert result.audio_capture_ok is True


def test_capture_microphone_until_pause_can_start_from_soft_speech_activity(monkeypatch) -> None:
    import numpy as np

    runtime = VoiceRuntime()
    monkeypatch.setattr(runtime, "_has_audio_capture_deps", lambda: True)
    monkeypatch.setattr(runtime, "_load_audio_capture_modules", lambda: (np, object()))
    monkeypatch.setattr(runtime, "_drain_audio_queue", lambda _queue: None)

    audio_queue: queue.Queue = queue.Queue()

    def _chunk(amplitude: int):
        return np.full((256, 1), amplitude, dtype=np.int16)

    # Calibration: 6 chunks (first 2 ignored, next 4 are baseline)
    calibration = [10] * 6
    # Speech: must exceed 'hard' threshold (calibrated from baseline 10 -> hard=35)
    speech = [1000] * 10
    # Silence: must be below 'silence' threshold (calibrated from 10 -> silence=12)
    # pause_chunks = pause_seconds (0.15) / chunk_seconds (0.05) = 3 chunks
    silence = [5] * 10
    
    for amplitude in calibration + speech + silence:
        audio_queue.put(_chunk(amplitude))

    monkeypatch.setattr(
        runtime,
        "_ensure_persistent_capture_session",
        lambda **_kwargs: {"queue": audio_queue},
    )

    wav_bytes = runtime.capture_microphone_until_pause(
        sample_rate=16000,
        channels=1,
        reuse_stream=True,
        chunk_seconds=0.05,
        pause_seconds=0.15,
        max_duration_seconds=1.0,
        max_initial_wait_seconds=0.5,
        speech_threshold=700.0,
        silence_threshold=220.0,
        soft_speech_threshold=260.0,
        soft_start_chunks=2,
    )

    assert wav_bytes[:4] == b"RIFF"
    assert runtime._last_capture_reason == ""


def test_voice_runtime_creator_verification_hides_sensitive_transcript(monkeypatch) -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"audio"
    runtime.core_runtime._pending_creator_verification = True
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: "jarvis 259")

    result = runtime.process_microphone_passive(duration_seconds=0.1)

    assert result.reason == ""
    assert "verification accepted" in result.text.lower()
    assert result.transcribed_text == "jarvis [hidden sensitive phrase]"


def test_pcm_to_wav_bytes_header() -> None:
    runtime = VoiceRuntime()
    pcm = b"\x01\x00\x02\x00\x03\x00\x04\x00"
    wav_bytes = runtime._pcm_to_wav_bytes(pcm, sample_rate=16000, channels=1)

    assert wav_bytes[:4] == b"RIFF"
    assert b"WAVE" in wav_bytes[:20]

from __future__ import annotations

from jarvis.observability.metrics import VoicePathMetrics
from jarvis.voice.runtime import VoiceRuntime


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


def test_voice_path_metrics_records_and_snapshot() -> None:
    metrics = VoicePathMetrics()
    metrics.record_requested_devices(input_device="Mic", output_device="Speakers")
    metrics.record_selected_devices(
        input_device={"index": 1, "name": "Mic"},
        output_device={"index": 6, "name": "Speakers"},
    )
    metrics.record_capture_settings(sample_rate=16000, capture_duration_seconds=3.0)
    metrics.record_capture(True)
    metrics.record_capture(False)
    metrics.record_transcribe(True)
    metrics.record_transcribe(False)
    metrics.record_turn()
    metrics.record_fallback("repeat_prompt")
    metrics.record_fallback("mic_unavailable")
    metrics.record_tts_backend("stub")
    metrics.record_tts_backend("stub")

    snapshot = metrics.snapshot()
    assert snapshot["capture_attempts"] == 2
    assert snapshot["capture_success"] == 1
    assert snapshot["capture_failures"] == 1
    assert snapshot["transcribe_attempts"] == 2
    assert snapshot["transcribe_success"] == 1
    assert snapshot["transcribe_failures"] == 1
    assert snapshot["turns_processed"] == 1
    assert snapshot["fallback_repeat_prompt"] == 1
    assert snapshot["fallback_mic_unavailable"] == 1
    assert snapshot["tts_backend_counts"]["stub"] == 2
    assert snapshot["requested_input_device"] == "Mic"
    assert snapshot["selected_input_device"]["index"] == 1
    assert snapshot["sample_rate"] == 16000
    assert snapshot["capture_duration_seconds"] == 3.0
    assert snapshot["audio_capture_ok"] is False
    assert snapshot["transcribe_ok"] is False
    assert snapshot["fallback_reason"] == "mic_unavailable"


def test_voice_runtime_metrics_updated_on_successful_audio() -> None:
    runtime = VoiceRuntime()
    runtime.process_audio(b"status")

    snapshot = runtime.metrics_snapshot()
    assert snapshot["transcribe_attempts"] == 1
    assert snapshot["transcribe_success"] == 1
    assert snapshot["turns_processed"] == 1
    assert sum(snapshot["tts_backend_counts"].values()) >= 1


def test_voice_runtime_metrics_updated_on_repeat_fallback() -> None:
    runtime = VoiceRuntime()
    runtime.process_audio(b"")

    snapshot = runtime.metrics_snapshot()
    assert snapshot["transcribe_attempts"] == 1
    assert snapshot["transcribe_failures"] == 1
    assert snapshot["fallback_repeat_prompt"] == 1


def test_voice_runtime_metrics_updated_on_mic_unavailable() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b""
    runtime.process_microphone(duration_seconds=0.1)

    snapshot = runtime.metrics_snapshot()
    assert snapshot["capture_attempts"] == 1
    assert snapshot["capture_failures"] == 1
    assert snapshot["fallback_mic_unavailable"] == 1
    assert snapshot["selected_input_device"]["name"] == "Default Mic"
    assert snapshot["selected_output_device"]["name"] == "Default Speakers"
    assert snapshot["audio_capture_ok"] is False
    assert snapshot["transcribe_ok"] is False
    assert snapshot["fallback_reason"] == "mic_unavailable"


def test_voice_runtime_metrics_include_device_details_on_successful_microphone_path() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _mock_devices()  # type: ignore[method-assign]
    runtime.capture_microphone = lambda **_kwargs: b"status"

    runtime.process_microphone(duration_seconds=0.25, sample_rate=22050)

    snapshot = runtime.metrics_snapshot()
    assert snapshot["selected_input_device"]["index"] == 1
    assert snapshot["selected_output_device"]["index"] == 6
    assert snapshot["sample_rate"] == 22050
    assert snapshot["capture_duration_seconds"] == 0.25
    assert snapshot["audio_capture_ok"] is True
    assert snapshot["transcribe_ok"] is True
    assert snapshot["fallback_reason"] == ""

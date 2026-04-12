from __future__ import annotations

from jarvis.voice.runtime import VoiceRuntime


def _devices() -> list[dict[str, object]]:
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
            "index": 4,
            "name": "Microphone (Q9-1)",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 44100,
            "is_default_input": False,
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
        {
            "index": 9,
            "name": "Studio Monitors",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 44100,
            "is_default_input": False,
            "is_default_output": False,
        },
    ]


def test_default_device_path_still_works_when_no_device_specified() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _devices()  # type: ignore[method-assign]

    seen: dict[str, int | None] = {}

    def fake_capture_microphone(**kwargs):
        seen["input_device"] = kwargs.get("input_device")
        seen["output_device"] = kwargs.get("output_device")
        return b"status"

    runtime.capture_microphone = fake_capture_microphone  # type: ignore[method-assign]

    result = runtime.process_microphone(duration_seconds=0.1, sample_rate=22050)

    assert result.ok is True
    assert seen["input_device"] == 1
    assert seen["output_device"] == 6
    assert result.selected_input_device["index"] == 1
    assert result.selected_output_device["index"] == 6
    assert result.sample_rate == 22050


def test_named_device_path_chooses_the_right_input() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _devices()  # type: ignore[method-assign]

    seen: dict[str, int | None] = {}

    def fake_capture_microphone(**kwargs):
        seen["input_device"] = kwargs.get("input_device")
        return b"status"

    runtime.capture_microphone = fake_capture_microphone  # type: ignore[method-assign]

    result = runtime.process_microphone(duration_seconds=0.1, input_device="Q9-1")

    assert result.ok is True
    assert seen["input_device"] == 4
    assert result.selected_input_device["name"] == "Microphone (Q9-1)"


def test_bad_device_name_returns_truthful_failure_not_silent_fallback() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _devices()  # type: ignore[method-assign]

    capture_called = {"value": False}

    def fake_capture_microphone(**_kwargs):
        capture_called["value"] = True
        return b"status"

    runtime.capture_microphone = fake_capture_microphone  # type: ignore[method-assign]

    result = runtime.process_microphone(duration_seconds=0.1, input_device="missing mic")

    assert result.ok is False
    assert result.reason == "input_device_not_found"
    assert result.fallback_reason == "input_device_not_found"
    assert "not found" in result.text.lower()
    assert capture_called["value"] is False


def test_output_device_must_match_current_default_playback_path() -> None:
    runtime = VoiceRuntime()
    runtime._list_audio_devices = lambda: _devices()  # type: ignore[method-assign]

    result = runtime.process_microphone(duration_seconds=0.1, output_device="Studio Monitors")

    assert result.ok is False
    assert result.reason == "output_device_not_active_default"
    assert result.selected_output_device["name"] == "Default Speakers"

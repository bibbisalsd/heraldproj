from __future__ import annotations
from jarvis.brain_core.speech_formatter import SpeechFormatter


def test_speech_formatter_redacts_windows_paths():
    text = r"Saved in C:\Users\example\Downloads\file.txt"
    formatted = SpeechFormatter().format(text)
    assert "C:\\Users" not in formatted
    assert "your local folder" in formatted


def test_speech_formatter_rewrites_internal_reason_code():
    formatted = SpeechFormatter().format("BG1_BUSY_ACTIVE")
    assert "heavy task lane is currently busy" in formatted


def test_speech_formatter_expands_time_meridiems_for_tts():
    formatted = SpeechFormatter().format("It's 5:21 pm.")
    assert "P M" in formatted
    assert "pm" not in formatted.lower()

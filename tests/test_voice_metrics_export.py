from __future__ import annotations

import json
from pathlib import Path

from jarvis.observability.voice_metrics_export import persist_voice_metrics


def _payload() -> dict:
    return {
        "lane": "realtime",
        "text": "I am online.",
        "ok": True,
        "reason": "",
        "transcribed_text": "status",
        "tts_backend": "stub",
        "tts_error": "",
        "voice_metrics": {
            "capture_attempts": 1,
            "capture_success": 1,
            "capture_failures": 0,
            "transcribe_attempts": 1,
            "transcribe_success": 1,
            "transcribe_failures": 0,
            "turns_processed": 1,
            "fallback_repeat_prompt": 0,
            "fallback_mic_unavailable": 0,
            "requested_input_device": "Mic",
            "requested_output_device": "Speakers",
            "selected_input_device": {"index": 1, "name": "Mic"},
            "selected_output_device": {"index": 6, "name": "Speakers"},
            "sample_rate": 16000,
            "capture_duration_seconds": 3.0,
            "audio_capture_ok": True,
            "transcribe_ok": True,
            "fallback_reason": "",
            "tts_backend_counts": {"stub": 1},
        },
    }


def test_persist_voice_metrics_creates_jsonl_and_csv(tmp_path) -> None:
    paths = persist_voice_metrics(_payload(), log_dir=str(tmp_path))

    jsonl = Path(paths["jsonl_path"])
    csv = Path(paths["csv_path"])

    assert jsonl.exists()
    assert csv.exists()


def test_persist_voice_metrics_appends_jsonl_lines(tmp_path) -> None:
    first = persist_voice_metrics(_payload(), log_dir=str(tmp_path))
    persist_voice_metrics(_payload(), log_dir=str(tmp_path))

    jsonl = Path(first["jsonl_path"])
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    parsed = [json.loads(line) for line in lines]
    assert all("voice_metrics" in item for item in parsed)


def test_persist_voice_metrics_writes_csv_header_once(tmp_path) -> None:
    first = persist_voice_metrics(_payload(), log_dir=str(tmp_path))
    persist_voice_metrics(_payload(), log_dir=str(tmp_path))

    csv_path = Path(first["csv_path"])
    rows = csv_path.read_text(encoding="utf-8").strip().splitlines()

    assert len(rows) == 3
    assert rows[0].startswith("timestamp,lane,text,ok,reason,transcribed_text,tts_backend")


def test_persist_voice_metrics_handles_missing_nested_metrics(tmp_path) -> None:
    payload = {
        "lane": "realtime",
        "text": "fallback",
        "tts_backend": "stub",
        "tts_error": "",
    }
    paths = persist_voice_metrics(payload, log_dir=str(tmp_path))
    csv_path = Path(paths["csv_path"])
    content = csv_path.read_text(encoding="utf-8")

    assert "capture_attempts" in content
    assert ",0," in content


def test_persist_voice_metrics_writes_device_details_columns(tmp_path) -> None:
    paths = persist_voice_metrics(_payload(), log_dir=str(tmp_path))
    csv_path = Path(paths["csv_path"])
    content = csv_path.read_text(encoding="utf-8")

    assert "selected_input_device" in content
    assert "fallback_reason" in content

from __future__ import annotations

import os
import time
from pathlib import Path

from jarvis.observability.voice_metrics_export import (
    list_voice_metric_files,
    persist_voice_metrics,
    prune_voice_metrics,
)


def _payload() -> dict:
    return {
        "lane": "realtime",
        "text": "I am online.",
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
            "tts_backend_counts": {"stub": 1},
        },
    }


def test_list_voice_metric_files_includes_csv_and_jsonl(tmp_path) -> None:
    paths = persist_voice_metrics(_payload(), log_dir=str(tmp_path))
    listed = list_voice_metric_files(str(tmp_path))

    assert paths["jsonl_path"] in listed
    assert paths["csv_path"] in listed


def test_prune_voice_metrics_removes_old_files_only(tmp_path) -> None:
    paths = persist_voice_metrics(_payload(), log_dir=str(tmp_path))
    jsonl = Path(paths["jsonl_path"])
    csv = Path(paths["csv_path"])

    old_time = time.time() - (20 * 24 * 3600)
    os.utime(jsonl, (old_time, old_time))
    os.utime(csv, (old_time, old_time))

    keep_file = tmp_path / "keep_me.txt"
    keep_file.write_text("x", encoding="utf-8")

    result = prune_voice_metrics(log_dir=str(tmp_path), retention_days=7)

    assert result["deleted_count"] == 2
    assert not jsonl.exists()
    assert not csv.exists()
    assert keep_file.exists()


def test_prune_voice_metrics_keeps_recent_files(tmp_path) -> None:
    paths = persist_voice_metrics(_payload(), log_dir=str(tmp_path))

    result = prune_voice_metrics(log_dir=str(tmp_path), retention_days=7)

    assert result["deleted_count"] == 0
    assert Path(paths["jsonl_path"]).exists()
    assert Path(paths["csv_path"]).exists()


def test_prune_voice_metrics_nonexistent_dir(tmp_path) -> None:
    missing = tmp_path / "missing"
    result = prune_voice_metrics(log_dir=str(missing), retention_days=7)

    assert result["deleted_count"] == 0
    assert result["remaining_count"] == 0
    assert result["deleted_files"] == []

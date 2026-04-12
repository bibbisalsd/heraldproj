from __future__ import annotations

import json
import os
import time
from pathlib import Path

from jarvis.maintenance.daily_ops import persist_ops_report, run_daily_ops
from jarvis.memory import Memory
from jarvis.observability.voice_metrics_export import list_voice_metric_files, persist_voice_metrics


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


def test_persist_ops_report_creates_jsonl_and_latest(tmp_path) -> None:
    report = {"timestamp": "2026-03-31T00:00:00+00:00", "retention": {"memory_deleted": 0}, "voice_smoke": None}
    paths = persist_ops_report(report, report_dir=str(tmp_path))

    jsonl = Path(paths["jsonl_path"])
    latest = Path(paths["latest_path"])

    assert jsonl.exists()
    assert latest.exists()

    latest_obj = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_obj["retention"]["memory_deleted"] == 0


def test_run_daily_ops_with_voice_smoke_and_report(tmp_path) -> None:
    db = tmp_path / "memory.sqlite"
    backups = tmp_path / "backups"
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"

    mem = Memory(db_path=str(db))
    mem.remember("k", "v", 0.9)
    mem.backup(backup_dir=str(backups))

    result = run_daily_ops(
        input_text="status",
        tts_backend="stub",
        memory_db_path=str(db),
        memory_retention_days=90,
        memory_backup_dir=str(backups),
        memory_backup_keep=1,
        voice_log_dir=str(logs),
        voice_metrics_retention_days=14,
        report_dir=str(reports),
        run_voice_smoke=True,
        persist_voice_payload=True,
    )

    assert result["voice_smoke"] is not None
    assert result["voice_smoke"]["tts_backend"] == "stub"
    assert Path(result["report_files"]["jsonl_path"]).exists()
    assert Path(result["report_files"]["latest_path"]).exists()


def test_run_daily_ops_without_voice_smoke(tmp_path) -> None:
    db = tmp_path / "memory.sqlite"
    result = run_daily_ops(
        memory_db_path=str(db),
        report_dir=str(tmp_path / "reports"),
        voice_log_dir=str(tmp_path / "logs"),
        run_voice_smoke=False,
    )

    assert result["voice_smoke"] is None


def test_run_daily_ops_restores_tts_backend_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_TTS_BACKEND", "auto")
    db = tmp_path / "memory.sqlite"

    run_daily_ops(
        input_text="status",
        tts_backend="stub",
        memory_db_path=str(db),
        voice_log_dir=str(tmp_path / "logs"),
        report_dir=str(tmp_path / "reports"),
        run_voice_smoke=False,
    )

    assert os.getenv("JARVIS_TTS_BACKEND") == "auto"


def test_run_daily_ops_prunes_old_voice_metrics(tmp_path) -> None:
    db = tmp_path / "memory.sqlite"
    logs = tmp_path / "logs"

    persist_voice_metrics(_payload(), log_dir=str(logs))
    old_ts = time.time() - (20 * 24 * 3600)
    for path in list_voice_metric_files(str(logs)):
        os.utime(path, (old_ts, old_ts))

    result = run_daily_ops(
        input_text="status",
        tts_backend="stub",
        memory_db_path=str(db),
        voice_log_dir=str(logs),
        voice_metrics_retention_days=7,
        report_dir=str(tmp_path / "reports"),
        run_voice_smoke=False,
    )

    assert result["retention"]["voice_metrics_deleted"] >= 2

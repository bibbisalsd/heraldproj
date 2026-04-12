from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.crsis.engine import CRSISEngine, persist_snapshot
from jarvis.maintenance.ops_history import list_ops_alert_files, persist_ops_alerts
from jarvis.maintenance.retention import run_retention
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


def test_run_retention_prunes_backups_and_voice_metrics(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite"
    backups = tmp_path / "backups"
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"
    crsis_logs = tmp_path / "crsis"

    memory = Memory(db_path=str(db_path))
    memory.remember("k", "v", 0.9)
    for _ in range(3):
        memory.backup(backup_dir=str(backups))

    persist_voice_metrics(_payload(), log_dir=str(logs))

    summary = {
        "report_count": 1,
        "voice_smoke_runs": 0,
        "voice_fallback_repeat_total": 0,
        "voice_fallback_mic_unavailable_total": 0,
        "health": {
            "status": "warn",
            "issues": [{"severity": "warn", "code": "test_alert", "message": "test"}],
        },
    }
    persist_ops_alerts(summary, report_dir=str(reports), source="retention_test")
    persist_snapshot(
        CRSISEngine().evaluate(signals=[]),
        log_dir=str(crsis_logs),
    )

    old_ts = time.time() - (20 * 24 * 3600)
    for path in list_voice_metric_files(str(logs)):
        os.utime(path, (old_ts, old_ts))
    for path in list_ops_alert_files(str(reports)):
        if Path(path).name.startswith("jarvis_ops_alerts_") and Path(path).name.endswith(".jsonl"):
            os.utime(path, (old_ts, old_ts))
    for path in Path(crsis_logs).glob("jarvis_crsis_*.jsonl"):
        os.utime(path, (old_ts, old_ts))

    result = run_retention(
        memory_db_path=str(db_path),
        memory_retention_days=90,
        memory_backup_dir=str(backups),
        memory_backup_keep=1,
        voice_log_dir=str(logs),
        voice_metrics_retention_days=7,
        ops_report_dir=str(reports),
        ops_alerts_retention_days=7,
        crsis_log_dir=str(crsis_logs),
        crsis_retention_days=7,
    )

    assert result["memory_backups_deleted"] >= 2
    assert result["voice_metrics_deleted"] == 2
    assert result["voice_metrics_remaining"] == 0
    assert result["ops_alerts_deleted"] == 1
    assert result["ops_alerts_remaining"] == 2
    assert result["crsis_deleted"] == 1
    assert result["crsis_remaining"] == 0


def test_run_retention_purges_old_memory_records(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite"
    backups = tmp_path / "backups"
    logs = tmp_path / "logs"

    memory = Memory(db_path=str(db_path))
    assert memory.remember("fact", "old", 0.9) is True
    assert memory.remember("fact", "new", 0.9) is True

    old_iso = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE memory_facts SET created_at = ? WHERE id = (SELECT MIN(id) FROM memory_facts)",
            (old_iso,),
        )
        conn.commit()

    result = run_retention(
        memory_db_path=str(db_path),
        memory_retention_days=7,
        memory_backup_dir=str(backups),
        memory_backup_keep=5,
        voice_log_dir=str(logs),
        voice_metrics_retention_days=14,
    )

    assert result["memory_deleted"] >= 1
    rows = memory.recall("fact")
    values = [row.value for row in rows]
    assert "new" in values

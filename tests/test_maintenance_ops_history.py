from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.maintenance.ops_history import (
    evaluate_and_persist_crsis,
    evaluate_ops_health,
    list_ops_alert_files,
    list_ops_report_files,
    load_ops_reports,
    persist_ops_alerts,
    prune_ops_alerts,
    render_ops_summary,
    summarize_ops_history,
)


def _report(
    ts: str,
    backend: str,
    mem_deleted: int,
    backups_deleted: int,
    voice_deleted: int,
    repeat: int,
    mic: int,
    alerts_deleted: int = 0,
) -> dict:
    return {
        "timestamp": ts,
        "voice_smoke": {
            "lane": "realtime",
            "text": "I am online.",
            "tts_backend": backend,
            "tts_error": "",
            "voice_metrics": {
                "fallback_repeat_prompt": repeat,
                "fallback_mic_unavailable": mic,
                "tts_backend_counts": {backend: 1},
            },
        },
        "retention": {
            "memory_deleted": mem_deleted,
            "memory_backups_deleted": backups_deleted,
            "voice_metrics_deleted": voice_deleted,
            "ops_alerts_deleted": alerts_deleted,
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row) + "\n")


def test_list_ops_report_files_sorted_newest_first(tmp_path) -> None:
    older = tmp_path / "jarvis_ops_report_2026-03-30.jsonl"
    newer = tmp_path / "jarvis_ops_report_2026-03-31.jsonl"
    _write_jsonl(older, [_report("2026-03-30T00:00:00+00:00", "stub", 1, 0, 0, 0, 0)])
    _write_jsonl(newer, [_report("2026-03-31T00:00:00+00:00", "sapi", 0, 1, 1, 1, 0)])

    old_ts = time.time() - 3600
    os.utime(older, (old_ts, old_ts))

    listed = list_ops_report_files(str(tmp_path))
    assert listed[0] == str(newer)
    assert listed[1] == str(older)


def test_load_ops_reports_respects_limit_and_order(tmp_path) -> None:
    day1 = tmp_path / "jarvis_ops_report_2026-03-30.jsonl"
    day2 = tmp_path / "jarvis_ops_report_2026-03-31.jsonl"

    _write_jsonl(
        day1,
        [
            _report("2026-03-30T01:00:00+00:00", "stub", 1, 1, 0, 0, 0),
            _report("2026-03-30T02:00:00+00:00", "stub", 2, 0, 1, 1, 0),
        ],
    )
    _write_jsonl(
        day2,
        [
            _report("2026-03-31T01:00:00+00:00", "sapi", 0, 1, 0, 0, 1),
            _report("2026-03-31T02:00:00+00:00", "sapi", 0, 0, 0, 0, 0),
        ],
    )

    now = time.time()
    os.utime(day1, (now - 3600, now - 3600))
    os.utime(day2, (now, now))

    loaded = load_ops_reports(str(tmp_path), limit=3)
    assert len(loaded) == 3
    assert loaded[0]["timestamp"] == "2026-03-31T02:00:00+00:00"
    assert loaded[1]["timestamp"] == "2026-03-31T01:00:00+00:00"
    assert loaded[2]["timestamp"] == "2026-03-30T02:00:00+00:00"


def test_summarize_ops_history_aggregates_values(tmp_path) -> None:
    day = tmp_path / "jarvis_ops_report_2026-03-31.jsonl"
    _write_jsonl(
        day,
        [
            _report("2026-03-31T01:00:00+00:00", "stub", 1, 2, 3, 1, 0, 4),
            _report("2026-03-31T02:00:00+00:00", "sapi", 4, 5, 6, 0, 2, 5),
        ],
    )

    summary = summarize_ops_history(str(tmp_path), limit=50)

    assert summary["report_count"] == 2
    assert summary["voice_smoke_runs"] == 2
    assert summary["voice_fallback_repeat_total"] == 1
    assert summary["voice_fallback_mic_unavailable_total"] == 2
    assert summary["tts_backend_counts"]["stub"] == 1
    assert summary["tts_backend_counts"]["sapi"] == 1
    assert summary["retention_totals"]["memory_deleted"] == 5
    assert summary["retention_totals"]["memory_backups_deleted"] == 7
    assert summary["retention_totals"]["voice_metrics_deleted"] == 9
    assert summary["retention_totals"]["ops_alerts_deleted"] == 9
    assert summary["time_range"]["newest"] == "2026-03-31T02:00:00+00:00"
    assert summary["time_range"]["oldest"] == "2026-03-31T01:00:00+00:00"


def test_summarize_ops_history_empty(tmp_path) -> None:
    summary = summarize_ops_history(str(tmp_path), limit=10)
    assert summary["report_count"] == 0
    assert summary["voice_smoke_runs"] == 0
    assert summary["retention_totals"]["memory_deleted"] == 0
    assert summary["retention_totals"]["ops_alerts_deleted"] == 0


def test_load_ops_reports_since_days_filters_old_records(tmp_path) -> None:
    day = tmp_path / "jarvis_ops_report_2026-03-31.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _write_jsonl(
        day,
        [
            _report(old, "stub", 1, 0, 0, 0, 0),
            _report(recent, "sapi", 0, 1, 0, 0, 0),
        ],
    )

    loaded = load_ops_reports(str(tmp_path), limit=10, since_days=7)
    assert len(loaded) == 1
    assert loaded[0]["timestamp"] == recent


def test_render_ops_summary_table_contains_key_lines(tmp_path) -> None:
    day = tmp_path / "jarvis_ops_report_2026-03-31.jsonl"
    _write_jsonl(day, [_report("2026-03-31T02:00:00+00:00", "stub", 2, 1, 3, 4, 5)])
    summary = summarize_ops_history(str(tmp_path), limit=10)
    summary["health"] = evaluate_ops_health(summary)

    rendered = render_ops_summary(summary, output_format="table")
    assert "Jarvis Ops Summary" in rendered
    assert "retention memory_deleted=2" in rendered
    assert "ops_alerts_deleted=0" in rendered
    assert "tts=stub:1" in rendered
    assert "health status=" in rendered


def test_evaluate_ops_health_warn_and_critical_states() -> None:
    warn_summary = {
        "report_count": 4,
        "voice_smoke_runs": 4,
        "voice_fallback_repeat_total": 2,
        "voice_fallback_mic_unavailable_total": 0,
    }
    warn = evaluate_ops_health(warn_summary, max_repeat_fallback_rate=0.4)
    assert warn["status"] == "warn"

    critical_summary = {
        "report_count": 4,
        "voice_smoke_runs": 4,
        "voice_fallback_repeat_total": 4,
        "voice_fallback_mic_unavailable_total": 0,
    }
    critical = evaluate_ops_health(critical_summary, max_repeat_fallback_rate=0.4)
    assert critical["status"] == "critical"


def test_persist_ops_alerts_writes_entries_and_latest_files(tmp_path) -> None:
    summary = {
        "health": {
            "status": "warn",
            "issues": [{"severity": "warn", "code": "low_coverage", "message": "coverage low"}],
        }
    }
    written = persist_ops_alerts(summary, report_dir=str(tmp_path), source="test")

    assert written["written"] == 1
    jsonl_path = Path(written["jsonl_path"])
    latest_json_path = Path(written["latest_json_path"])
    latest_text_path = Path(written["latest_text_path"])
    assert jsonl_path.exists()
    assert latest_json_path.exists()
    assert latest_text_path.exists()
    assert "low_coverage" in latest_text_path.read_text(encoding="utf-8")


def test_prune_ops_alerts_removes_old_daily_files_keeps_latest(tmp_path) -> None:
    summary = {
        "health": {
            "status": "warn",
            "issues": [{"severity": "warn", "code": "test", "message": "test issue"}],
        }
    }
    persist_ops_alerts(summary, report_dir=str(tmp_path), source="test")
    old_ts = time.time() - (20 * 24 * 3600)
    for path in list_ops_alert_files(str(tmp_path)):
        p = Path(path)
        if p.name.startswith("jarvis_ops_alerts_") and p.name.endswith(".jsonl"):
            os.utime(p, (old_ts, old_ts))

    pruned = prune_ops_alerts(str(tmp_path), retention_days=7)
    assert pruned["deleted_count"] == 1
    assert Path(tmp_path / "jarvis_ops_alerts_latest.json").exists()
    assert Path(tmp_path / "jarvis_ops_alerts_latest.txt").exists()


def test_evaluate_and_persist_crsis_writes_snapshot_files(tmp_path) -> None:
    summary = {
        "report_count": 12,
        "health": {
            "voice_smoke_coverage": 0.40,
            "repeat_fallback_rate": 0.10,
            "mic_unavailable_rate": 0.05,
            "thresholds": {
                "min_voice_smoke_coverage": 0.50,
                "max_repeat_fallback_rate": 0.25,
                "max_mic_unavailable_rate": 0.25,
            },
        },
    }

    result = evaluate_and_persist_crsis(summary, report_dir=str(tmp_path), source="ops_history_test")
    assert result["status"] == "warn"
    assert Path(result["files"]["jsonl_path"]).exists()
    assert Path(result["files"]["latest_path"]).exists()
    assert any(finding["signal_key"] == "voice_smoke_coverage" for finding in result["findings"])

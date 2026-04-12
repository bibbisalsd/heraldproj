from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jarvis.maintenance.daily_ops import persist_ops_report


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script test is Windows-only")
def test_daily_ops_history_script_outputs_summary_json(tmp_path) -> None:
    report_dir = tmp_path / "reports"
    persist_ops_report(
        {
            "timestamp": "2026-03-31T10:00:00+00:00",
            "voice_smoke": {
                "voice_metrics": {
                    "fallback_repeat_prompt": 1,
                    "fallback_mic_unavailable": 0,
                    "tts_backend_counts": {"stub": 1},
                }
            },
            "retention": {
                "memory_deleted": 2,
                "memory_backups_deleted": 1,
                "voice_metrics_deleted": 0,
            },
        },
        report_dir=str(report_dir),
    )

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "daily_ops_history.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ReportDir",
            str(report_dir),
            "-Limit",
            "10",
            "-OutputFormat",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["report_count"] >= 1
    assert payload["retention_totals"]["memory_deleted"] >= 2
    assert payload["health"]["status"] in {"ok", "warn", "critical"}


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script test is Windows-only")
def test_daily_ops_history_script_table_and_since_days(tmp_path) -> None:
    report_dir = tmp_path / "reports"
    persist_ops_report(
        {
            "timestamp": "2026-03-31T10:00:00+00:00",
            "voice_smoke": {
                "voice_metrics": {
                    "fallback_repeat_prompt": 0,
                    "fallback_mic_unavailable": 1,
                    "tts_backend_counts": {"sapi": 1},
                }
            },
            "retention": {
                "memory_deleted": 0,
                "memory_backups_deleted": 0,
                "voice_metrics_deleted": 1,
            },
        },
        report_dir=str(report_dir),
    )

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "daily_ops_history.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ReportDir",
            str(report_dir),
            "-Limit",
            "10",
            "-SinceDays",
            "30",
            "-OutputFormat",
            "table",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Jarvis Ops Summary" in completed.stdout
    assert "voice" in completed.stdout
    assert "health status=" in completed.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script test is Windows-only")
def test_daily_ops_history_script_fail_on_warn_sets_exit_code(tmp_path) -> None:
    report_dir = tmp_path / "reports"
    persist_ops_report(
        {
            "timestamp": "2026-03-31T10:00:00+00:00",
            "voice_smoke": {
                "voice_metrics": {
                    "fallback_repeat_prompt": 1,
                    "fallback_mic_unavailable": 0,
                    "tts_backend_counts": {"stub": 1},
                }
            },
            "retention": {
                "memory_deleted": 0,
                "memory_backups_deleted": 0,
                "voice_metrics_deleted": 0,
            },
        },
        report_dir=str(report_dir),
    )

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "daily_ops_history.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ReportDir",
            str(report_dir),
            "-OutputFormat",
            "json",
            "-MaxRepeatFallbackRate",
            "0.2",
            "-FailOnWarn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["health"]["status"] in {"warn", "critical"}

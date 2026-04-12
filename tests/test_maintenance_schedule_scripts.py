from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell scheduled task scripts are Windows-only")
def test_install_daily_ops_task_preview_outputs_expected_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "install_daily_ops_task.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-TaskName",
            "JarvisDailyOpsPreviewTest",
            "-DailyTime",
            "04:15",
            "-PreviewOnly",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["preview_only"] is True
    assert payload["task_name"] == "JarvisDailyOpsPreviewTest"
    assert payload["daily_time"] == "04:15"
    assert "powershell.exe" in payload["command"]
    assert "-HealthSinceDays 7" in payload["command"]
    assert "-MaxRepeatFallbackRate 0.25" in payload["command"]
    assert "-OpsAlertsRetentionDays 30" in payload["command"]
    assert "-CrsisRetentionDays 30" in payload["command"]
    assert "/Create" in payload["create_args"]


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell scheduled task scripts are Windows-only")
def test_remove_daily_ops_task_preview_outputs_expected_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "remove_daily_ops_task.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-TaskName",
            "JarvisDailyOpsPreviewTest",
            "-PreviewOnly",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["preview_only"] is True
    assert payload["task_name"] == "JarvisDailyOpsPreviewTest"
    assert "/Delete" in payload["delete_args"]

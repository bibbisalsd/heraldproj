from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script test is Windows-only")
def test_daily_ops_script_outputs_history_health_json(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "daily_ops.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-InputText",
            "status",
            "-TtsBackend",
            "stub",
            "-MemoryDbPath",
            str(tmp_path / "memory.sqlite"),
            "-MemoryBackupDir",
            str(tmp_path / "backups"),
            "-VoiceLogDir",
            str(tmp_path / "logs"),
            "-ReportDir",
            str(tmp_path / "reports"),
            "-NoVoicePersist",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert "history_health" in payload
    assert "history_alerts" in payload
    assert "history_crsis" in payload
    assert payload["history_health"]["status"] in {"ok", "warn", "critical"}
    assert payload["history_crsis"]["status"] in {"ok", "warn", "critical"}


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script test is Windows-only")
def test_daily_ops_script_fail_on_warn_returns_nonzero(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "daily_ops.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-NoVoiceSmoke",
            "-FailOnWarn",
            "-MemoryDbPath",
            str(tmp_path / "memory.sqlite"),
            "-MemoryBackupDir",
            str(tmp_path / "backups"),
            "-VoiceLogDir",
            str(tmp_path / "logs"),
            "-ReportDir",
            str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["history_health"]["status"] in {"warn", "critical"}


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script test is Windows-only")
def test_daily_ops_script_fail_on_critical_returns_exit_2(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "daily_ops.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-InputText",
            "status",
            "-TtsBackend",
            "stub",
            "-MaxRepeatFallbackRate",
            "-0.1",
            "-FailOnCritical",
            "-MemoryDbPath",
            str(tmp_path / "memory.sqlite"),
            "-MemoryBackupDir",
            str(tmp_path / "backups"),
            "-VoiceLogDir",
            str(tmp_path / "logs"),
            "-ReportDir",
            str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["history_health"]["status"] == "critical"

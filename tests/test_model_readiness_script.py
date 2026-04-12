from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script tests are Windows-only")
def test_model_readiness_script_outputs_json() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "model_readiness.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputFormat",
            "json",
            "-SkipVoice",
            "-OllamaBin",
            "not-a-real-ollama-bin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["overall_status"] == "not_ready"
    assert "required_models_missing" in payload["blockers"]


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script tests are Windows-only")
def test_model_readiness_script_fail_on_not_ready_returns_nonzero() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "model_readiness.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputFormat",
            "json",
            "-SkipVoice",
            "-OllamaBin",
            "not-a-real-ollama-bin",
            "-FailOnNotReady",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["overall_status"] == "not_ready"


from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script tests are Windows-only")
def test_setup_models_script_reports_list_failure_for_missing_binary() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "setup_models.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OllamaBin",
            "not-a-real-ollama-bin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    error_text = f"{completed.stdout}\n{completed.stderr}".lower()
    assert "ollama list failed" in error_text


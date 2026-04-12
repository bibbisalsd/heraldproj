from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script tests are Windows-only")
def test_accept_target_stack_script_outputs_report() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "accept_target_stack.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-SkipCompile",
            "-SkipVoiceMic",
            "-OllamaBin",
            "not-a-real-ollama-bin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["overall_status"] in {"pass", "warn"}
    assert payload["readiness"]["exit_code"] == 0
    assert payload["readiness"]["payload"]["overall_status"] == "not_ready"
    assert payload["voice_text"]["payload"]["tts_backend"] == "kokoro"


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script tests are Windows-only")
def test_accept_target_stack_script_reports_invalid_input_device_truthfully() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "accept_target_stack.ps1"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-SkipCompile",
            "-SkipVoiceText",
            "-RunVoiceMic",
            "-InputDevice",
            "definitely-missing-device",
            "-OllamaBin",
            "not-a-real-ollama-bin",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["overall_status"] == "warn"
    assert payload["voice_mic"]["payload"]["reason"] == "input_device_not_found"
    assert payload["voice_mic"]["assessment"]["capture_status"] == "fail"

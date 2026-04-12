"""Voice diagnostics - extended metrics and health reporting."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import audio_device


@dataclass
class VoiceDiagnosticsResult:
    """Comprehensive voice diagnostics output."""

    timestamp: str
    overall_status: str  # "ok", "partial", "degraded"

    # Device selection
    requested_input_device: str | int | None
    requested_output_device: str | int | None
    selected_input_device: dict[str, Any] | None
    selected_output_device: dict[str, Any] | None

    # Capture settings
    sample_rate: int | None
    capture_duration_seconds: float | None

    # Capture status
    audio_capture_ok: bool | None
    capture_error: str | None

    # Transcription status
    transcribe_ok: bool | None
    transcribed_text: str | None
    transcription_confidence: float | None
    stt_error: str | None

    # TTS status
    tts_backend: str | None
    tts_error: str | None
    tts_spoke: bool

    # Fallback info
    fallback_reason: str | None

    # Device availability
    available_input_devices: list[str]
    available_output_devices: list[str]
    default_input_device: str | None
    default_output_device: str | None

    # System info
    python_version: str
    platform: str
    sounddevice_available: bool
    faster_whisper_available: bool
    kokoro_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class VoiceDiagnostics:
    """Voice diagnostics collector and reporter."""

    def __init__(self, log_dir: str = "./logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def collect(
        self,
        input_device: str | int | None = None,
        output_device: str | int | None = None,
        sample_rate: int = 16000,
        duration_seconds: float = 3.0,
        test_text: str = "status",
    ) -> VoiceDiagnosticsResult:
        """Collect comprehensive voice diagnostics.

        Args:
            input_device: Requested input device (index or name)
            output_device: Requested output device (index or name)
            sample_rate: Sample rate for capture
            duration_seconds: Duration for capture test
            test_text: Text to use for TTS test

        Returns:
            VoiceDiagnosticsResult with all diagnostic data
        """
        from .runtime import VoiceRuntime

        timestamp = datetime.now(timezone.utc).isoformat()

        # Check package availability
        import importlib.util

        sounddevice_available = importlib.util.find_spec("sounddevice") is not None
        faster_whisper_available = (
            importlib.util.find_spec("faster_whisper") is not None
        )
        kokoro_available = self._check_kokoro_available()

        # Get device summary
        device_summary = audio_device.get_device_summary()

        # Initialize result
        result = VoiceDiagnosticsResult(
            timestamp=timestamp,
            overall_status="ok",
            requested_input_device=input_device,
            requested_output_device=output_device,
            selected_input_device=None,
            selected_output_device=None,
            sample_rate=sample_rate,
            capture_duration_seconds=duration_seconds,
            audio_capture_ok=None,
            capture_error=None,
            transcribe_ok=None,
            transcribed_text=None,
            transcription_confidence=None,
            stt_error=None,
            tts_backend=None,
            tts_error=None,
            tts_spoke=False,
            fallback_reason=None,
            available_input_devices=device_summary["input_devices"],
            available_output_devices=device_summary["output_devices"],
            default_input_device=device_summary["default_input"],
            default_output_device=device_summary["default_output"],
            python_version=sys.version.split()[0],
            platform=sys.platform,
            sounddevice_available=sounddevice_available,
            faster_whisper_available=faster_whisper_available,
            kokoro_available=kokoro_available,
        )

        # Check for missing dependencies
        missing_deps = []
        if not sounddevice_available:
            missing_deps.append("sounddevice")
        if not faster_whisper_available:
            missing_deps.append("faster_whisper")

        if missing_deps:
            result.overall_status = "degraded"
            result.capture_error = f"missing_dependencies:{','.join(missing_deps)}"
            return result

        # Test full voice path
        try:
            rt = VoiceRuntime()

            # Process audio (text-to-speech path)
            audio_result = rt.process_audio(test_text.encode("utf-8"))

            # Populate result from audio_result
            result.selected_input_device = audio_result.selected_input_device
            result.selected_output_device = audio_result.selected_output_device
            result.audio_capture_ok = audio_result.audio_capture_ok
            result.transcribe_ok = audio_result.transcribe_ok
            result.transcribed_text = audio_result.transcribed_text
            result.fallback_reason = audio_result.fallback_reason or None
            result.tts_backend = rt.tts.last_backend
            result.tts_error = rt.tts.last_error or None
            result.tts_spoke = bool(rt.tts.last_spoken)
            result.stt_error = rt.stt.last_error or None

            # Determine overall status
            if not result.audio_capture_ok:
                result.overall_status = "degraded"
            elif not result.transcribe_ok:
                result.overall_status = "partial"
            elif result.fallback_reason:
                result.overall_status = "partial"

        except Exception as e:
            result.overall_status = "degraded"
            result.capture_error = f"runtime_error:{type(e).__name__}:{str(e)}"

        return result

    def _check_kokoro_available(self) -> bool:
        """Check if Kokoro TTS is available."""
        import importlib.util

        # Check module
        if importlib.util.find_spec("kokoro") is not None:
            return True

        # Check pack
        pack_dir = os.getenv("JARVIS_KOKORO_PACK_DIR", "")
        if pack_dir:
            launcher = Path(pack_dir) / "jarvis_launcher.py"
            if launcher.exists():
                return True

        return False

    def save_diagnostics(
        self,
        result: VoiceDiagnosticsResult,
        prefix: str = "voice_diagnostics",
    ) -> str:
        """Save diagnostics result to JSON file.

        Args:
            result: Diagnostics result to save
            prefix: Filename prefix

        Returns:
            Path to saved file
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.to_json(indent=2))

        # Also save as latest
        latest_path = self.log_dir / f"{prefix}_latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(result.to_json(indent=2))

        return str(filepath)

    def get_quick_status(self) -> dict[str, Any]:
        """Get quick voice subsystem status without running full test.

        Returns dict with:
            - status: "ok", "partial", "degraded"
            - sounddevice: bool
            - faster_whisper: bool
            - kokoro: bool
            - input_devices: int
            - output_devices: int
            - issues: list of issue strings
        """
        import importlib.util

        issues = []
        sounddevice_ok = importlib.util.find_spec("sounddevice") is not None
        whisper_ok = importlib.util.find_spec("faster_whisper") is not None
        kokoro_ok = self._check_kokoro_available()

        if not sounddevice_ok:
            issues.append("sounddevice not installed")
        if not whisper_ok:
            issues.append("faster_whisper not installed")

        device_summary = audio_device.get_device_summary()
        input_count = len(device_summary["input_devices"])
        output_count = len(device_summary["output_devices"])

        if input_count == 0:
            issues.append("no input devices found")
        if output_count == 0:
            issues.append("no output devices found")

        status = "ok"
        if len(issues) > 2:
            status = "degraded"
        elif issues:
            status = "partial"

        return {
            "status": status,
            "sounddevice": sounddevice_ok,
            "faster_whisper": whisper_ok,
            "kokoro": kokoro_ok,
            "input_devices": input_count,
            "output_devices": output_count,
            "issues": issues,
        }


def build_voice_diagnostics(
    input_device: str | int | None = None,
    output_device: str | int | None = None,
    sample_rate: int = 16000,
    duration_seconds: float = 3.0,
    test_text: str = "status",
    log_dir: str = "./logs",
) -> dict[str, Any]:
    """Build voice diagnostics report.

    Convenience function for use in scripts.
    """
    diag = VoiceDiagnostics(log_dir=log_dir)
    result = diag.collect(
        input_device=input_device,
        output_device=output_device,
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        test_text=test_text,
    )
    return result.to_dict()

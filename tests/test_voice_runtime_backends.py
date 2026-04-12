from __future__ import annotations

from pathlib import Path
import subprocess

import jarvis.voice.tts as tts_module
from jarvis.voice.runtime import VoiceRuntime
from jarvis.voice.tts import TTS


def test_tts_defaults_to_kokoro_backend(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_TTS_BACKEND", raising=False)
    tts = TTS()
    assert tts.backend == "kokoro"


def test_tts_uses_bundled_pack_by_default(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_USE_KOKORO_PACK", raising=False)
    monkeypatch.delenv("JARVIS_KOKORO_PACK_DIR", raising=False)
    monkeypatch.delenv("JARVIS_KOKORO_PYTHON", raising=False)

    tts = TTS()

    assert Path(tts.kokoro_pack_dir, "jarvis_launcher.py").exists()
    assert tts.kokoro_pack_enabled is True

    monkeypatch.setattr(tts, "_speak_kokoro_pack", lambda _text: (True, ""))
    result = tts.speak("hello there")

    assert result["backend"] == "kokoro"
    assert result["error"] == ""


def test_tts_empty_text_returns_error_payload() -> None:
    tts = TTS()
    result = tts.speak("   ")
    assert result["ok"] == "false"
    assert result["error"] == "empty_text"


def test_tts_auto_falls_back_to_stub_when_backends_unavailable(monkeypatch) -> None:
    tts = TTS()
    tts.backend = "auto"
    monkeypatch.setattr(tts, "_has_kokoro", lambda: False)
    monkeypatch.setattr(tts, "_speak_windows_sapi", lambda _text: (False, "sapi_missing"))

    result = tts.speak("hello there")
    assert result["ok"] == "true"
    assert result["backend"] == "stub"
    assert result["error"] == "sapi_missing"


def test_tts_sapi_backend_invokes_powershell(monkeypatch) -> None:
    tts = TTS()
    tts.backend = "sapi"

    monkeypatch.setattr(tts_module.sys, "platform", "win32")

    called = {"value": False}

    def fake_run(*_args, **_kwargs):
        called["value"] = True
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts_module.subprocess, "run", fake_run)

    result = tts.speak("speak now")
    assert called["value"] is True
    assert result["backend"] == "sapi"


def test_tts_kokoro_backend_reports_missing_when_unavailable(monkeypatch) -> None:
    tts = TTS()
    tts.backend = "kokoro"
    monkeypatch.setattr(tts, "_has_kokoro", lambda: False)

    result = tts.speak("hello there")
    assert result["backend"] == "stub"
    assert result["error"] == "kokoro_unavailable"


def test_voice_runtime_empty_audio_prompts_repeat() -> None:
    runtime = VoiceRuntime()
    result = runtime.process_audio(b"")

    assert result.lane == "realtime"
    assert "please repeat" in result.text.lower()
    assert runtime.tts.last_spoken == result.text


def test_voice_runtime_handles_stt_failure(monkeypatch) -> None:
    runtime = VoiceRuntime()
    monkeypatch.setattr(runtime.stt, "transcribe", lambda _audio: (_ for _ in ()).throw(RuntimeError("stt failed")))

    result = runtime.process_audio(b"bytes")
    assert result.lane == "realtime"
    assert "please repeat" in result.text.lower()


def test_tts_pack_success_reports_kokoro_backend(monkeypatch, tmp_path) -> None:
    pack_dir = tmp_path / "kokoro_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "jarvis_launcher.py").write_text("print('stub')", encoding="utf-8")

    monkeypatch.setenv("JARVIS_USE_KOKORO_PACK", "true")
    monkeypatch.setenv("JARVIS_KOKORO_PACK_DIR", str(pack_dir))

    tts = TTS()
    tts.backend = "auto"
    monkeypatch.setattr(tts, "_speak_kokoro_pack", lambda _text: (True, ""))

    result = tts.speak("hello there")
    assert result["backend"] == "kokoro"
    assert result["error"] == ""


def test_tts_pack_failure_falls_back_to_sapi(monkeypatch, tmp_path) -> None:
    pack_dir = tmp_path / "kokoro_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "jarvis_launcher.py").write_text("print('stub')", encoding="utf-8")

    monkeypatch.setenv("JARVIS_USE_KOKORO_PACK", "true")
    monkeypatch.setenv("JARVIS_KOKORO_PACK_DIR", str(pack_dir))

    tts = TTS()
    tts.backend = "auto"
    monkeypatch.setattr(tts, "_speak_kokoro_pack", lambda _text: (False, "pack_failed"))
    monkeypatch.setattr(tts, "_speak_windows_sapi", lambda _text: (True, ""))

    result = tts.speak("hello there")
    assert result["backend"] == "sapi"


def test_tts_pack_prefers_configured_python(monkeypatch, tmp_path) -> None:
    pack_dir = tmp_path / "kokoro_pack"
    pack_dir.mkdir(parents=True)
    launcher = pack_dir / "jarvis_launcher.py"
    launcher.write_text("print('stub')", encoding="utf-8")

    configured_python = tmp_path / "venv-python.exe"
    configured_python.write_text("", encoding="utf-8")

    monkeypatch.setenv("JARVIS_KOKORO_PYTHON", str(configured_python))

    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts_module.subprocess, "run", fake_run)

    tts = TTS()
    ok, error = tts._speak_kokoro_pack("hello there")

    assert ok is True
    assert error == ""
    assert seen["args"][0] == str(configured_python)
    assert seen["args"][1] == str(launcher)
    assert seen["cwd"] == str(pack_dir)

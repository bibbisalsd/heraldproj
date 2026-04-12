from __future__ import annotations

from pathlib import Path

from jarvis.specialists.specialist_vision import run as run_vision
from jarvis.tools.ocr_read import read as read_ocr
from jarvis.tools.screen_capture import capture as capture_screen
from jarvis.tools.vision_lite import analyze_screen


def test_screen_capture_reports_unavailable_when_native_capture_unavailable(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")

    monkeypatch.chdir(workspace)
    # Patch both Windows and Linux capture backends to simulate unavailability
    monkeypatch.setattr("jarvis.tools.screen_capture._try_windows_capture", lambda path, target="screen": False)
    monkeypatch.setattr("jarvis.tools.screen_capture._try_mss_capture", lambda path, target="screen": None)
    monkeypatch.setattr("jarvis.tools.screen_capture._try_gnome_screenshot", lambda path, target="screen": None)
    monkeypatch.setattr("jarvis.tools.screen_capture._try_scrot_capture", lambda path, target="screen": None)
    monkeypatch.setattr("jarvis.tools.screen_capture._try_import_screenshot", lambda path, target="screen": None)

    result = capture_screen("./artifacts/test_capture.png")

    assert result["ok"] is False
    assert result["mode"] == "unavailable"
    assert result["reason"].startswith("native_capture_unavailable")
    path = Path(result["path"])
    assert not path.exists()


def test_ocr_read_uses_sidecar_text(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image = workspace / "diagram.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    sidecar = workspace / "diagram.ocr.txt"
    sidecar.write_text("Build pipeline status: green", encoding="utf-8")

    monkeypatch.chdir(workspace)

    result = read_ocr(str(image))

    assert result["ok"] is True
    assert result["mode"] == "sidecar"
    assert "Build pipeline status: green" in result["text"]


def test_ocr_read_uses_windows_backend_when_no_sidecar(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image = workspace / "diagram.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        "jarvis.tools.ocr_read._read_windows_ocr",
        lambda *args, **kwargs: {
            "ok": True,
            "available": True,
            "text": "Detected live OCR text",
            "mode": "windows_ocr",
            "backend": "windows_media_ocr",
        },
    )

    result = read_ocr(str(image))

    assert result["ok"] is True
    assert result["mode"] == "windows_ocr"
    assert result["backend"] == "windows_media_ocr"
    assert "Detected live OCR text" in result["text"]


def test_vision_lite_reports_capture_unavailable(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        "jarvis.tools.vision_lite.capture",
        lambda path, target="screen": {
            "ok": False,
            "reason": "native_capture_unavailable",
            "mode": "unavailable",
            "path": path,
            "target": target,
        },
    )

    result = analyze_screen("./artifacts/test_capture.png")

    assert result["ok"] is False
    assert result["reason"] == "native_capture_unavailable"
    assert result["capture_mode"] == "unavailable"


def test_vision_lite_reports_missing_ocr_text(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image = workspace / "artifacts" / "vision_capture" / "captured.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\ncaptured")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        "jarvis.tools.vision_lite.capture",
        lambda path, target="screen": {"ok": True, "path": str(image), "mode": "native", "target": target},
    )

    result = analyze_screen("./artifacts/test_capture.png")

    assert result["ok"] is False
    assert result["reason"] == "ocr_text_unavailable"
    assert result["ocr_mode"] == "none"


def test_vision_lite_reports_windows_ocr_mode(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image = workspace / "artifacts" / "vision_capture" / "captured.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\ncaptured")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        "jarvis.tools.vision_lite.capture",
        lambda path, target="screen": {"ok": True, "path": str(image), "mode": "native", "target": target},
    )
    monkeypatch.setattr(
        "jarvis.tools.vision_lite.ocr_read",
        lambda path: {
            "ok": True,
            "text": "Login screen",
            "mode": "windows_ocr",
            "backend": "windows_media_ocr",
            "image_path": path,
        },
    )

    result = analyze_screen("./artifacts/test_capture.png")

    assert result["ok"] is True
    assert result["analysis_mode"] == "ocr_windows_ocr"
    assert result["ocr_backend"] == "windows_media_ocr"


def test_specialist_vision_captures_screen_and_appends_ocr(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    captured = workspace / "artifacts" / "vision_capture" / "captured.png"
    captured.parent.mkdir(parents=True, exist_ok=True)
    captured.write_bytes(b"\x89PNG\r\n\x1a\ncaptured")
    (workspace / "artifacts" / "vision_capture" / "captured.ocr.txt").write_text(
        "Sign-in form with username and password fields.",
        encoding="utf-8",
    )

    seen: dict[str, str] = {}

    def fake_capture(_path: str, target: str = "screen", **kwargs) -> dict:
        return {"ok": True, "path": str(captured), "mode": "native", "target": target}

    def fake_analyze(task: str, model: str | None = None) -> dict:
        seen["task"] = task
        seen["model"] = model or ""
        return {"ok": True, "summary": "done", "model": model}

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.specialists.specialist_vision.capture_screen", fake_capture)
    monkeypatch.setattr("jarvis.specialists.specialist_vision.analyze_vision", fake_analyze)
    monkeypatch.setattr(
        "jarvis.specialists.specialist_vision.active_window_current",
        lambda: {
            "ok": True,
            "window_title": "Settings",
            "process_name": "SystemSettings.exe",
            "pid": 4242,
        },
    )

    result = run_vision("analyze this screenshot for UI structure", model="qwen3-vl:test")

    assert result["ok"] is True
    assert result["capture_mode"] == "native"
    assert result["capture_target"] == "screen"
    assert result["active_window"]["window_title"] == "Settings"
    assert result["active_window"]["process_name"] == "SystemSettings.exe"
    assert str(captured.resolve()) in seen["task"]
    assert "Active window context" in seen["task"]
    assert "- title: Settings" in seen["task"]
    assert "- process: SystemSettings.exe" in seen["task"]
    assert "OCR context" in seen["task"]
    assert "username and password fields" in seen["task"]
    assert seen["model"] == "qwen3-vl:test"


def test_specialist_vision_reports_capture_unavailable(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        "jarvis.specialists.specialist_vision.capture_screen",
        lambda path, target="screen", **kwargs: {
            "ok": False,
            "path": path,
            "mode": "unavailable",
            "reason": "native_capture_unavailable",
            "target": target,
        },
    )

    result = run_vision("analyze this screenshot for UI structure", model="qwen3-vl:test")

    assert result["ok"] is False
    assert result["reason"] == "native_capture_unavailable"
    assert result["capture_mode"] == "unavailable"
    assert result["capture_target"] == "screen"
    assert "native_capture_unavailable" in result["result"]

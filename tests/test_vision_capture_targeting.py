from __future__ import annotations

import shutil
from pathlib import Path

from jarvis.specialists.specialist_vision import run as run_vision


def _workspace(name: str) -> Path:
    root = Path("logs") / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    return root


def test_specialist_vision_prefers_foreground_window_capture(monkeypatch) -> None:
    workspace = _workspace("vision_targeting_foreground")
    seen: dict[str, str] = {}

    def fake_capture(path: str, target: str = "screen") -> dict:
        seen["target"] = target
        return {
            "ok": False,
            "path": path,
            "mode": "unavailable",
            "reason": "foreground_window_capture_unavailable",
            "target": target,
        }

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.specialists.specialist_vision.capture_screen", fake_capture)

    result = run_vision("analyze this active window for UI issues", model="qwen3-vl:test")

    assert seen["target"] == "foreground_window"
    assert result["capture_target"] == "foreground_window"
    assert result["reason"] == "foreground_window_capture_unavailable"


def test_specialist_vision_prefers_full_screen_when_requested(monkeypatch) -> None:
    workspace = _workspace("vision_targeting_screen")
    seen: dict[str, str] = {}

    def fake_capture(path: str, target: str = "screen") -> dict:
        seen["target"] = target
        return {
            "ok": False,
            "path": path,
            "mode": "unavailable",
            "reason": "native_capture_unavailable",
            "target": target,
        }

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.specialists.specialist_vision.capture_screen", fake_capture)

    result = run_vision("analyze the whole screen for layout issues", model="qwen3-vl:test")

    assert seen["target"] == "screen"
    assert result["capture_target"] == "screen"
    assert result["reason"] == "native_capture_unavailable"

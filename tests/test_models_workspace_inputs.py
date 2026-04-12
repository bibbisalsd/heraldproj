from __future__ import annotations

import base64
from types import SimpleNamespace

from jarvis.models.code import analyze as analyze_code
from jarvis.models.vision import analyze as analyze_vision


def test_code_model_includes_workspace_file_context(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    target = workspace / "example.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    captured: dict[str, list[str]] = {"prompts": []}

    class FakeClient:
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            captured["prompts"].append(prompt)
            return SimpleNamespace(ok=True, text="done")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.models.code.OllamaClient", FakeClient)

    result = analyze_code(f'please debug "{target}"', model="deepcoder:test")

    assert result["ok"] is True
    combined_prompts = " ".join(captured["prompts"])
    assert "Workspace File Context" in combined_prompts
    assert "example.py" in combined_prompts
    assert "def add(a, b):" in combined_prompts


def test_vision_model_sends_workspace_images_via_chat(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image_path = workspace / "screen.png"
    image_bytes = b"\x89PNG\r\n\x1a\nfake-image"
    image_path.write_bytes(image_bytes)

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt: str, images: list[str] | None = None, **kwargs) -> SimpleNamespace:
            captured["prompt"] = prompt
            if images:
                captured["images"] = images
            return SimpleNamespace(ok=True, text="looks correct")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.models.vision.OllamaClient", FakeClient)

    result = analyze_vision(f'analyze "{image_path}"', model="qwen3-vl:test")

    assert result["ok"] is True
    assert result["image_count"] == 1
    assert str(image_path.resolve()) in captured["prompt"]
    assert "images" in captured
    assert base64.b64decode(captured["images"][0]) == image_bytes

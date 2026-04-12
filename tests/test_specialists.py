from __future__ import annotations
from jarvis.specialists.specialist_code import run as run_code
from jarvis.specialists.specialist_vision import run as run_vision


def test_specialist_code_contract():
    result = run_code("write function")
    assert result["ok"] is True
    assert "Code specialist" in result["result"]


def test_specialist_vision_contract(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image = workspace / "diagram.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    def fake_analyze(task: str, model: str | None = None) -> dict:
        return {"ok": True, "image_ref": task, "model": model, "summary": "done"}

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.specialists.specialist_vision.analyze_vision", fake_analyze)

    result = run_vision(f'analyze "{image}"')
    assert result["ok"] is True
    assert result["image_count"] == 1
    assert "Vision specialist result" in result["result"]


def test_specialist_code_passes_model_to_analyzer(monkeypatch):
    captured = {"model": None}

    def fake_analyze(task: str, model: str | None = None) -> dict:
        captured["model"] = model
        return {"ok": True, "task": task, "model": model, "summary": "done"}

    monkeypatch.setattr("jarvis.specialists.specialist_code.analyze_code", fake_analyze)
    run_code("write function", model="deepcoder:test")
    assert captured["model"] == "deepcoder:test"


def test_specialist_vision_passes_model_to_analyzer(monkeypatch, tmp_path):
    captured = {"model": None}
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    image = workspace / "diagram.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    def fake_analyze(task: str, model: str | None = None) -> dict:
        captured["model"] = model
        return {"ok": True, "image_ref": task, "model": model, "summary": "done"}

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.specialists.specialist_vision.analyze_vision", fake_analyze)
    run_vision(f'analyze "{image}"', model="qwen3-vl:test")
    assert captured["model"] == "qwen3-vl:test"

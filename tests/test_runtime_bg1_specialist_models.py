from __future__ import annotations

from dataclasses import replace

from jarvis.main import JarvisRuntime


def test_runtime_bg1_code_specialist_uses_config_model(monkeypatch) -> None:
    runtime = JarvisRuntime()
    runtime.config = replace(runtime.config, code_bg1_model="deepcoder:custom")
    captured: dict[str, str] = {}

    def fake_run(summary: str, **kwargs: Any) -> dict:
        captured["summary"] = summary
        captured["model"] = kwargs.get("model") or ""
        return {"ok": True, "result": "Code specialist result: done"}

    monkeypatch.setattr("jarvis.brain_core.bg1_manager.run_specialist_code", fake_run)
    result = runtime.bg1_manager._execute_bg1_specialist("please debug this function")
    assert captured["summary"] == "please debug this function"
    assert captured["model"] == "deepcoder:custom"
    assert "Code specialist result" in result


def test_runtime_bg1_vision_specialist_uses_config_model(monkeypatch) -> None:
    runtime = JarvisRuntime()
    runtime.config = replace(runtime.config, vision_bg1_model="qwen3-vl:custom")
    captured: dict[str, str] = {}

    def fake_run(summary: str, **kwargs: Any) -> dict:
        captured["summary"] = summary
        captured["model"] = kwargs.get("model") or ""
        return {"ok": True, "result": "Vision specialist result: done"}

    monkeypatch.setattr("jarvis.brain_core.bg1_manager.run_specialist_vision", fake_run)
    result = runtime.bg1_manager._execute_bg1_specialist("analyze screenshot from this image")
    assert captured["summary"] == "analyze screenshot from this image"
    assert captured["model"] == "qwen3-vl:custom"
    assert "Vision specialist result" in result

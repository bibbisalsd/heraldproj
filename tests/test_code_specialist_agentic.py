from __future__ import annotations

from types import SimpleNamespace

from jarvis.models.code import analyze as analyze_code
from jarvis.specialists.specialist_code import run as run_code


def test_code_specialist_uses_tool_observations_for_explicit_python_file(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    target = workspace / "broken.py"
    target.write_text("def broken(:\n    pass\n", encoding="utf-8")

    captured: dict[str, list[str]] = {"prompts": []}

    class FakeClient:
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            captured["prompts"].append(prompt)
            return SimpleNamespace(ok=True, text="diagnosis")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.models.code.OllamaClient", FakeClient)

    result = analyze_code(f'please debug "{target}"', model="deepcoder:test")

    assert result["ok"] is True
    # Generator prompt is usually the first one
    combined_prompts = " ".join(captured["prompts"])
    assert str(target.resolve()) in combined_prompts
    assert "Tool Observations" in combined_prompts
    assert "Python syntax check failed" in combined_prompts


def test_code_specialist_can_search_workspace_by_keyword_when_no_path_is_given(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    target = workspace / "payment_service.py"
    target.write_text("def charge_card():\n    return True\n", encoding="utf-8")

    captured: dict[str, list[str]] = {"prompts": []}

    class FakeClient:
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            captured["prompts"].append(prompt)
            return SimpleNamespace(ok=True, text="done")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.models.code.OllamaClient", FakeClient)

    result = analyze_code("please debug the payment service flow", model="deepcoder:test")

    assert result["ok"] is True
    combined_prompts = " ".join(captured["prompts"])
    assert str(target.resolve()) in combined_prompts
    assert "Read " in combined_prompts


def test_code_specialist_fallback_includes_tool_summary_when_model_is_unavailable(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    target = workspace / "worker.py"
    target.write_text("def run_job():\n    return 1\n", encoding="utf-8")

    class FakeClient:
        def __init__(self, model: str) -> None:
            self.model = model

        def run(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(ok=False, error="ollama_not_installed")

    monkeypatch.chdir(workspace)
    monkeypatch.setattr("jarvis.models.code.OllamaClient", FakeClient)

    result = run_code(f'please debug "{target}"', model="deepcoder:test")

    assert result["ok"] is True
    assert "ollama_not_installed" in result["result"]
    assert "Python syntax check passed" in result["result"]

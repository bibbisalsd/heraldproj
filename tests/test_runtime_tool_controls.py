from __future__ import annotations

from pathlib import Path

from jarvis.brain_core.tool_orchestrator import ToolOrchestrator
from jarvis.main import JarvisRuntime
from jarvis.tools.time_tool import utc_now_iso


def test_tool_orchestrator_requires_confirmation_for_risky_tool() -> None:
    orchestrator = ToolOrchestrator()
    orchestrator.register_tool(
        "dangerous",
        lambda: {"ok": True},
        confirmation_action="code_runner",
    )

    result = orchestrator.execute("dangerous")

    assert result.ok is False
    assert "confirmation_required" in result.safety_flags


def test_tool_orchestrator_runs_safe_tool_without_confirmation() -> None:
    orchestrator = ToolOrchestrator()
    orchestrator.register_tool("utc_now", utc_now_iso)

    result = orchestrator.execute("utc_now")

    assert result.ok is True


def test_tool_orchestrator_propagates_tool_reported_failure() -> None:
    orchestrator = ToolOrchestrator()
    orchestrator.register_tool("failing_tool", lambda: {"ok": False, "reason": "unsupported"})

    result = orchestrator.execute("failing_tool")

    assert result.ok is False
    assert result.summary == "unsupported"
    assert result.data["result"]["reason"] == "unsupported"


def test_runtime_invoke_tool_denies_guest_file_write(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    monkeypatch.chdir(workspace)

    runtime = JarvisRuntime()
    result = runtime.invoke_tool("file_write", profile="guest", path="note.txt", content="hello")

    assert result["ok"] is False
    assert result["reason"] == "capability_denied"
    assert result["capability"] == "file_write"
    assert not (workspace / "note.txt").exists()


def test_runtime_invoke_tool_requires_confirmation_for_owner_file_write(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    monkeypatch.chdir(workspace)

    runtime = JarvisRuntime()
    result = runtime.invoke_tool("file_write", profile="owner", path="note.txt", content="hello")

    assert result["ok"] is False
    assert "confirmation_required" in result["safety_flags"]
    assert not (workspace / "note.txt").exists()


def test_runtime_invoke_tool_allows_confirmed_owner_file_write(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    monkeypatch.chdir(workspace)

    runtime = JarvisRuntime()
    result = runtime.invoke_tool(
        "file_write",
        profile="owner",
        confirmed=True,
        path="note.txt",
        content="hello",
    )

    assert result["ok"] is True
    assert (workspace / "note.txt").read_text(encoding="utf-8") == "hello"


def test_runtime_invoke_tool_requires_confirmation_for_owner_app_launch() -> None:
    runtime = JarvisRuntime()

    denied = runtime.invoke_tool("app_launch", profile="owner", app_name="calculator")
    allowed = runtime.invoke_tool("app_launch", profile="owner", confirmed=True, app_name="calculator")

    assert denied["ok"] is False
    assert "confirmation_required" in denied["safety_flags"]
    assert allowed["ok"] is False
    assert allowed["summary"] == "app_executable_not_found"
    assert allowed["data"]["result"]["action"] == "launch"
    assert allowed["data"]["result"]["app"] == "calculator"

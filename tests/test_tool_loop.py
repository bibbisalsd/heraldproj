from __future__ import annotations
from jarvis.brain_core.tool_orchestrator import ToolOrchestrator
from jarvis.tools.time_tool import utc_now_iso


def test_tool_orchestrator_runs_registered_tool():
    orchestrator = ToolOrchestrator()
    orchestrator.register_tool("utc_now", utc_now_iso)
    result = orchestrator.execute("utc_now")
    assert result.ok is True
    assert "result" in result.data


def test_tool_orchestrator_rejects_missing_tool():
    orchestrator = ToolOrchestrator()
    result = orchestrator.execute("missing")
    assert result.ok is False
    assert "unknown_tool" in result.safety_flags

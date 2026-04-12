from __future__ import annotations
from jarvis.brain_core.guardrails import Guardrails
from jarvis.config import capability_map


def test_guardrails_blocks_paths_outside_workspace(tmp_path):
    root = str(tmp_path / "workspace")
    outside = str(tmp_path / ".." / "outside.txt")
    decision = Guardrails().check_path_safety(outside, root)
    assert decision.allowed is False
    assert decision.reason == "path_outside_workspace"


def test_guardrails_requires_confirmation_for_risky_actions():
    decision = Guardrails().check_confirmation_required("file_write")
    assert decision.allowed is False
    assert decision.reason == "confirmation_required"


def test_permission_map_denies_guest_risky_capabilities():
    caps = capability_map()["guest"]
    assert caps["file_write"] is False
    assert caps["code_runner"] is False
    assert caps["heavy_tasks"] is False

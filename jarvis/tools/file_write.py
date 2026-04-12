from __future__ import annotations

from pathlib import Path

from jarvis.brain_core.guardrails import Guardrails


def write(path: str, content: str, workspace_root: str) -> dict:
    decision = Guardrails().check_path_safety(path, workspace_root)
    if not decision.allowed:
        return {"ok": False, "reason": decision.reason}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p)}

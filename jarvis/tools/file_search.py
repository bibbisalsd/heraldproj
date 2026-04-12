from __future__ import annotations

from pathlib import Path

from jarvis.brain_core.guardrails import Guardrails
from jarvis.models.workspace_inputs import workspace_root


def search(root: str, query: str) -> dict:
    base = Path(root)
    safe_root = workspace_root(base)
    decision = Guardrails().check_path_safety(str(base.resolve()), str(safe_root))
    if not decision.allowed:
        return {"ok": False, "reason": decision.reason, "matches": []}
    if not base.exists():
        return {"ok": False, "reason": "not_found", "matches": []}
    matches: list[str] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if query.lower() in path.name.lower():
            matches.append(str(path))
        if len(matches) >= 100:
            break
    return {"ok": True, "matches": matches}

from __future__ import annotations

from jarvis.models.workspace_inputs import resolve_workspace_path


def read(path: str) -> dict:
    resolved = resolve_workspace_path(path)
    if resolved is None or not resolved.exists():
        return {"ok": False, "reason": "not_found_or_unsafe"}
    return {
        "ok": True,
        "path": str(resolved),
        "content": resolved.read_text(encoding="utf-8", errors="replace"),
    }

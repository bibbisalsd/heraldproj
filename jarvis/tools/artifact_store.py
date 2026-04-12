from __future__ import annotations

from pathlib import Path

from jarvis.brain_core.guardrails import Guardrails
from jarvis.models.workspace_inputs import resolve_workspace_target


def _resolve_artifact_path(
    artifact_dir: str, name: str
) -> tuple[Path | None, str | None]:
    base = resolve_workspace_target(artifact_dir)
    if base is None:
        return None, "path_outside_workspace"

    # Explicitly check for '..' traversal before joining.
    if ".." in name or ".." in name.replace("\\", "/"):
        return None, "path_outside_artifact_dir"

    try:
        target = (base / name).resolve()
    except OSError:
        return None, "invalid_artifact_path"

    decision = Guardrails().check_path_safety(str(target), str(base))
    if not decision.allowed:
        return None, "path_outside_artifact_dir"
    return target, None


def store_text(artifact_dir: str, name: str, content: str) -> dict:
    path, error = _resolve_artifact_path(artifact_dir, name)
    if path is None:
        return {"ok": False, "reason": error}

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "reason": f"artifact_write_failed:{type(exc).__name__}"}
    return {"ok": True, "path": str(path)}

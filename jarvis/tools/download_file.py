from __future__ import annotations

from jarvis.models.workspace_inputs import resolve_workspace_target
from .network_guard import validate


def download(url: str, destination: str) -> dict:
    check = validate(url)
    if not check["ok"]:
        return {"ok": False, "reason": check["reason"]}

    path = resolve_workspace_target(destination)
    if path is None:
        return {"ok": False, "reason": "path_outside_workspace"}

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"downloaded-from:{url}", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "reason": f"download_write_failed:{type(exc).__name__}"}
    return {"ok": True, "path": str(path)}

from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

from jarvis.models.workspace_inputs import resolve_workspace_path


def run_python(code: str, timeout_seconds: int = 10) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "code": proc.returncode,
    }


def compile_python_file(path: str) -> dict:
    resolved = resolve_workspace_path(path)
    if resolved is None or not resolved.is_file():
        return {"ok": False, "reason": "not_found_or_unsafe", "path": path}

    target = Path(resolved)
    try:
        py_compile.compile(str(target), doraise=True)
        return {"ok": True, "path": str(target), "reason": "syntax_ok"}
    except py_compile.PyCompileError as exc:
        return {
            "ok": False,
            "path": str(target),
            "reason": "syntax_error",
            "error": str(exc),
        }


def run_python_json(code: str, timeout_seconds: int = 10) -> dict:
    result = run_python(code, timeout_seconds=timeout_seconds)
    if not result.get("ok"):
        return result
    try:
        payload = json.loads(result.get("stdout", "").strip() or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "reason": "invalid_json",
            "stdout": result.get("stdout", ""),
        }
    return {"ok": True, "payload": payload}

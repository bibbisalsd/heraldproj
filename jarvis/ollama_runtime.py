from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_ollama_bin(ollama_bin: str = "ollama") -> str:
    requested = (ollama_bin or "ollama").strip() or "ollama"
    if requested != "ollama":
        return requested

    from_path = shutil.which("ollama")
    if from_path:
        return from_path

    for candidate in _default_ollama_candidates():
        if candidate.exists():
            return str(candidate)
    return requested


def _default_ollama_candidates() -> list[Path]:
    candidates: list[Path] = []
    local_appdata = os.getenv("LOCALAPPDATA", "").strip()
    program_files = os.getenv("ProgramFiles", "").strip()

    if local_appdata:
        base = Path(local_appdata) / "Programs" / "Ollama"
        candidates.extend([base / "ollama.exe", base / "Ollama.exe"])
    if program_files:
        base = Path(program_files) / "Ollama"
        candidates.extend([base / "ollama.exe", base / "Ollama.exe"])
    return candidates

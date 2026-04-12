from __future__ import annotations

import base64
import re
from pathlib import Path

from ..brain_core.guardrails import Guardrails

_TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".psd1",
    ".psm1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

_IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
_PATH_TOKEN_PATTERN = re.compile(
    r"[A-Za-z]:[\\/][^\s\"']+|(?:\.{0,2}[\\/])?[^\s\"']+\.[A-Za-z0-9]{1,8}"
)


def workspace_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "GEMINI.md").exists() or (candidate / "CLAUDE.md").exists():
            return candidate
    return current


def extract_candidate_paths(text: str) -> list[str]:
    candidates: list[str] = []

    for pattern in (r'"([^"\r\n]+)"', r"'([^'\r\n]+)'"):
        for match in re.finditer(pattern, text):
            value = match.group(1).strip()
            if value and (_looks_like_path(value) or Path(value).suffix):
                candidates.append(value)

    for match in _PATH_TOKEN_PATTERN.finditer(text):
        value = match.group(0).strip().rstrip(".,;:!?)]}")
        if value:
            candidates.append(value)

    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def resolve_workspace_path(candidate: str, base_dir: Path | None = None) -> Path | None:
    resolved = resolve_workspace_target(candidate, base_dir=base_dir)
    if resolved is None or not resolved.exists():
        return None
    return resolved


def resolve_workspace_target(
    candidate: str, base_dir: Path | None = None
) -> Path | None:
    raw = candidate.strip().strip("\"'").rstrip(".,;:!?)]}")
    if not raw:
        return None

    base = (base_dir or Path.cwd()).resolve()
    root = workspace_root(base)
    candidate_path = Path(raw)
    if not candidate_path.is_absolute():
        candidate_path = base / candidate_path

    try:
        resolved = candidate_path.resolve()
    except OSError:
        return None

    decision = Guardrails().check_path_safety(str(resolved), str(root))
    if not decision.allowed:
        return None
    return resolved


def collect_text_context(
    task: str,
    *,
    base_dir: Path | None = None,
    max_files: int = 3,
    max_chars_per_file: int = 1600,
) -> list[dict[str, str]]:
    contexts: list[dict[str, str]] = []
    for candidate in extract_candidate_paths(task):
        resolved = resolve_workspace_path(candidate, base_dir=base_dir)
        if resolved is None or not resolved.is_file():
            continue
        if resolved.suffix.lower() not in _TEXT_EXTENSIONS:
            continue

        text = resolved.read_text(encoding="utf-8", errors="replace")
        snippet = text[:max_chars_per_file]
        contexts.append(
            {
                "path": str(resolved),
                "snippet": snippet,
            }
        )
        if len(contexts) >= max_files:
            break
    return contexts


def collect_image_inputs(
    task: str,
    *,
    base_dir: Path | None = None,
    max_images: int = 3,
) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for candidate in extract_candidate_paths(task):
        resolved = resolve_workspace_path(candidate, base_dir=base_dir)
        if resolved is None or not resolved.is_file():
            continue
        if resolved.suffix.lower() not in _IMAGE_EXTENSIONS:
            continue

        payload = base64.b64encode(resolved.read_bytes()).decode("ascii")
        images.append(
            {
                "path": str(resolved),
                "base64": payload,
            }
        )
        if len(images) >= max_images:
            break
    return images


def _looks_like_path(value: str) -> bool:
    return any(token in value for token in ("\\", "/", ":")) or bool(Path(value).suffix)


# Aliases for backward compatibility
def resolve_workspace_root(start: str | Path | None = None) -> Path:
    return workspace_root(Path(start) if isinstance(start, str) else start)

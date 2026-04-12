from __future__ import annotations

import os
import re
from pathlib import Path

from ..tools.code_runner import compile_python_file
from ..tools.document_parse import parse as parse_document
from ..tools.file_read import read as read_file
from ..tools.file_search import search as search_files
from .ollama_client import OllamaClient
from .workspace_inputs import (
    collect_text_context,
    extract_candidate_paths,
    resolve_workspace_path,
    workspace_root,
)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "bug",
    "code",
    "debug",
    "deeply",
    "error",
    "file",
    "fix",
    "for",
    "function",
    "help",
    "in",
    "issue",
    "look",
    "please",
    "problem",
    "refactor",
    "script",
    "test",
    "this",
    "with",
}


def analyze(
    task: str, model: str | None = None, reviewer_model: str | None = None
) -> dict:
    """Analyze code task using a two-pass Sequential Relay Architecture.

    Pass 1: Generate initial logic/fix using the primary coding model (deepcoder:14b).
    Pass 2: Review and profile the result using the reviewer model (rnj-1:8b).
    """
    primary_model = model or os.getenv("JARVIS_CODE_BG1_MODEL", "deepcoder:14b")
    reviewer_model = reviewer_model or os.getenv(
        "JARVIS_CODE_REVIEWER_MODEL", "rnj-1:8b"
    )

    tool_state = _gather_tool_context(task)

    # --- Pass 1: Generation ---
    client_gen = OllamaClient(model=primary_model)
    gen_prompt = _build_prompt(task, tool_state)
    gen_result = client_gen.run(gen_prompt, keep_alive="0")

    if not gen_result.ok:
        fallback = _fallback_summary(gen_result.error, tool_state)
        return {
            "ok": False,
            "task": task,
            "model": primary_model,
            "summary": fallback,
            "tool_summary": tool_state["summary"],
            "files_considered": tool_state["files_considered"],
        }

    initial_code = gen_result.text or ""

    # Force unload the primary model before loading the reviewer to save VRAM
    client_gen.run("", keep_alive="0")

    # --- Pass 2: Review/Profile ---
    client_rev = OllamaClient(model=reviewer_model)
    rev_prompt = _build_review_prompt(task, initial_code)
    rev_result = client_rev.run(rev_prompt, keep_alive="0")

    final_output = rev_result.text if rev_result.ok else initial_code

    return {
        "ok": True,
        "task": task,
        "model": f"{primary_model} -> {reviewer_model}"
        if rev_result.ok
        else primary_model,
        "summary": final_output or "no_output",
        "tool_summary": tool_state["summary"],
        "files_considered": tool_state["files_considered"],
        "reviewed": rev_result.ok,
    }


def _build_review_prompt(task: str, initial_code: str) -> str:
    return f"""You are a senior code reviewer and performance profiler.
Your task is to review, optimize, and verify the following code/fix generated for the task: "{task}"

Initial Code/Analysis:
---
{initial_code}
---

Review Guidelines:
1. Verify logical correctness against the task.
2. Identify any performance bottlenecks or suboptimal patterns.
3. If errors are found, provide the corrected version.
4. If the code is good, add a brief profiling note.

Return the final optimized version and a short summary of changes/verification."""


def _build_prompt(task: str, tool_state: dict[str, object]) -> str:
    sections = [
        "You are a local code specialist.",
        "Use the provided tool observations and workspace file context before answering.",
        "Return a concise diagnosis, likely fix, and any concrete next checks.",
        f"Task: {task}",
    ]

    observations = tool_state["observations"]
    if isinstance(observations, list) and observations:
        sections.append(
            "Tool Observations:\n" + "\n".join(f"- {item}" for item in observations)
        )

    contexts = tool_state["contexts"]
    if isinstance(contexts, list) and contexts:
        file_sections = []
        for item in contexts:
            snippet = str(item.get("snippet", "")).strip() or "<empty file>"
            file_sections.append(f"Path: {item['path']}\n```text\n{snippet}\n```")
        sections.append("Workspace File Context:\n" + "\n\n".join(file_sections))

    sections.append(
        "If the evidence is incomplete, say what is inferred versus directly observed from the tool context."
    )
    return "\n\n".join(sections)


def _gather_tool_context(task: str) -> dict[str, object]:
    root = workspace_root()
    explicit_paths = _explicit_file_paths(task)

    # NEW: Skip searching if it's a creation task with no explicit paths
    is_creation = any(
        word in task.lower() for word in ["write", "create", "new", "generate"]
    )
    searched_paths = []
    if not is_creation or explicit_paths:
        searched_paths = _search_candidate_files(task, root)

    candidate_paths = _dedupe_paths([*explicit_paths, *searched_paths])[:3]

    contexts = []
    observations: list[str] = []
    files_considered: list[str] = []

    if not candidate_paths:
        contexts = collect_text_context(task)
        files_considered = [
            str(item.get("path", "")) for item in contexts if item.get("path")
        ]
        if contexts:
            observations.append(
                "Used direct workspace file context from referenced files."
            )
        else:
            observations.append(
                "No relevant workspace files were detected from the task text."
            )
    else:
        for path in candidate_paths:
            files_considered.append(path)
            file_payload = read_file(path)
            if not file_payload.get("ok"):
                observations.append(
                    f"Could not read {path}: {file_payload.get('reason', 'read_failed')}."
                )
                continue

            parse_payload = parse_document(path)
            preview = (
                str(parse_payload.get("preview", "")) if parse_payload.get("ok") else ""
            )
            contexts.append({"path": path, "snippet": preview[:1600]})

            chars = (
                int(
                    parse_payload.get(
                        "chars", len(str(file_payload.get("content", "")))
                    )
                )
                if parse_payload.get("ok")
                else len(str(file_payload.get("content", "")))
            )
            observations.append(f"Read {path} ({chars} chars).")

            suffix = Path(path).suffix.lower()
            if suffix == ".py":
                compile_payload = compile_python_file(path)
                if compile_payload.get("ok"):
                    observations.append(f"Python syntax check passed for {path}.")
                else:
                    error_text = str(
                        compile_payload.get(
                            "error",
                            compile_payload.get("reason", "syntax_check_failed"),
                        )
                    )
                    observations.append(
                        f"Python syntax check failed for {path}: {error_text[:220]}"
                    )

    summary = " | ".join(observations[:4]) if observations else "no_tool_observations"
    return {
        "contexts": contexts[:3],
        "observations": observations[:6],
        "summary": summary,
        "files_considered": files_considered[:3],
    }


def _explicit_file_paths(task: str) -> list[str]:
    resolved: list[str] = []
    for candidate in extract_candidate_paths(task):
        path = resolve_workspace_path(candidate)
        if path is None or not path.is_file():
            continue
        if path.suffix.lower() not in {
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
        }:
            continue
        resolved.append(str(path))
    return _dedupe_paths(resolved)


def _search_candidate_files(task: str, root: Path) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_.-]+", task.lower())
    keywords = [word for word in words if len(word) >= 4 and word not in _STOPWORDS]
    matches: list[str] = []
    for keyword in keywords[:3]:
        result = search_files(str(root), keyword)
        if not result.get("ok"):
            continue
        for match in result.get("matches", [])[:4]:
            path = resolve_workspace_path(str(match), base_dir=root)
            if path is None or not path.is_file():
                continue
            if path.suffix.lower() not in {
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
            }:
                continue
            matches.append(str(path))
        if len(matches) >= 3:
            break
    return _dedupe_paths(matches)


def _dedupe_paths(paths: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(str(path))
    return ordered


def _fallback_summary(error: str, tool_state: dict[str, object]) -> str:
    tool_summary = str(tool_state.get("summary", "")).strip()
    error_text = error.strip() or "model_unavailable"

    msg = f"Model generation failed: {error_text}."
    if tool_summary and tool_summary != "no_tool_observations":
        msg += f" Workspace context: {tool_summary}"
    return msg

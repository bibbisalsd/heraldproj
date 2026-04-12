from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jarvis.models.workspace_inputs import (
    extract_candidate_paths,
    resolve_workspace_path,
    workspace_root,
)
from jarvis.tools.active_window_info import current as active_window_current
from jarvis.tools.ocr_read import read as ocr_read
from jarvis.tools.screen_capture import capture as capture_screen
from jarvis.models.vision import analyze as analyze_vision


# Phase 2C: Vision Depth - Specialist Routing
# Route OCR-only tasks to OCR engine, visual reasoning to vision model
_OCR_ONLY_HINTS = {
    "read text",
    "extract text",
    "ocr",
    "transcribe",
    "copy text",
    "what does it say",
    "what does this say",
    "text from image",
}
_VISUAL_REASONING_HINTS = {
    "what is",
    "describe",
    "explain",
    "analyze",
    "identify",
    "what color",
    "what shape",
    "how many",
    "count",
    "find",
    "locate",
    "where is",
    "screenshot",
    "screen",
    "window",
}


def run(task: str, model: str | None = None, use_smart_crop: bool = True) -> dict:
    (
        prepared_task,
        image_paths,
        ocr_notes,
        capture_meta,
        active_window,
        capture_target,
        is_ocr_only,
    ) = _prepare_vision_task(task)
    capture_mode = capture_meta.get("mode", "") if capture_meta else ""
    if not image_paths:
        reason = "no_image_inputs"
        if capture_meta and not capture_meta.get("ok", False):
            reason = str(capture_meta.get("reason", reason))
        return {
            "ok": False,
            "task": task,
            "prepared_task": prepared_task,
            "image_paths": image_paths,
            "ocr_notes": ocr_notes,
            "capture_mode": capture_mode,
            "capture_target": capture_target,
            "active_window": active_window,
            "reason": reason,
            "result": f"Vision specialist unavailable: {reason}",
            "retryable": True,
            "model": model,
        }

    # Phase 2C: Specialist Routing - skip vision LLM for OCR-only tasks
    if is_ocr_only and ocr_notes:
        snippet = " ".join(ocr_notes)[:350]
        return {
            "ok": True,
            "task": task,
            "prepared_task": prepared_task,
            "image_paths": image_paths,
            "ocr_notes": ocr_notes,
            "capture_mode": capture_mode,
            "capture_target": capture_target,
            "active_window": active_window,
            "image_count": len(image_paths),
            "result": f"Vision specialist result (OCR-only): {snippet}",
            "retryable": False,
            "model": "ocr_engine",
            "provenance": "observed",
        }

    result = analyze_vision(prepared_task, model=model)
    if result.get("ok"):
        summary = str(result.get("summary", "")).strip()
        snippet = summary[:350] if summary else "done"
        return {
            "ok": True,
            "task": task,
            "prepared_task": prepared_task,
            "image_paths": image_paths,
            "ocr_notes": ocr_notes,
            "capture_mode": capture_mode,
            "capture_target": capture_target,
            "active_window": active_window,
            "image_count": len(image_paths),
            "result": f"Vision specialist result: {snippet}",
            "retryable": False,
            "model": result.get("model"),
            "provenance": "inferred",
        }
    reason = (
        str(result.get("summary", "model_unavailable")).strip() or "model_unavailable"
    )
    return {
        "ok": False,
        "task": task,
        "prepared_task": prepared_task,
        "image_paths": image_paths,
        "ocr_notes": ocr_notes,
        "capture_mode": capture_mode,
        "capture_target": capture_target,
        "active_window": active_window,
        "image_count": len(image_paths),
        "reason": reason,
        "result": f"Vision specialist unavailable: {reason}",
        "retryable": True,
        "model": result.get("model"),
        "provenance": "inferred",
    }


def _prepare_vision_task(
    task: str,
) -> tuple[str, list[str], list[str], dict | None, dict | None, str, bool]:
    image_paths = _extract_image_paths(task)
    capture_meta: dict | None = None
    active_window: dict | None = None
    capture_target = "screen"

    if not image_paths and _needs_screen_capture(task):
        capture_target = _capture_target_for_task(task)
        root = workspace_root()
        capture_dir = root / "artifacts" / "vision_capture"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        target = capture_dir / f"screen_{stamp}.png"
        # Phase 2C: Use smart crop for foreground_window captures
        use_smart_crop = capture_target == "foreground_window"
        capture_meta = capture_screen(
            str(target), target=capture_target, smart_crop=use_smart_crop
        )
        if capture_meta.get("ok"):
            captured_path = str(Path(str(capture_meta["path"])).resolve())
            image_paths.append(captured_path)
            active_window = _normalize_active_window(active_window_current())

    prepared_task = task
    if image_paths:
        prepared_task = (
            prepared_task.rstrip()
            + "\n\nWorkspace image inputs:\n"
            + "\n".join(f'- "{path}"' for path in image_paths)
        )
        if capture_meta is not None:
            prepared_task = (
                prepared_task.rstrip() + f"\n\nCapture target: {capture_target}"
            )

    if active_window:
        window_lines = ["Active window context:"]
        if active_window.get("window_title"):
            window_lines.append(f"- title: {active_window['window_title']}")
        if active_window.get("process_name"):
            window_lines.append(f"- process: {active_window['process_name']}")
        prepared_task = prepared_task.rstrip() + "\n\n" + "\n".join(window_lines)

    ocr_notes: list[str] = []
    ocr_data: list[
        dict
    ] = []  # Phase 2C: Store structured OCR data with confidence/boxes

    # Phase 2C: Specialist Routing - detect OCR-only tasks
    is_ocr_only = _is_ocr_only_task(task)

    for path in image_paths:
        # Phase 2C: Include confidence scores and bounding boxes for OCR
        ocr = ocr_read(path, include_confidence=True, include_boxes=False)
        text = str(ocr.get("text", "")).strip()
        if text:
            compact = " ".join(text.split())
            ocr_notes.append(f"{path}: {compact[:500]}")
            # Store structured data for potential use
            if "words" in ocr:
                ocr_data.append(
                    {
                        "path": path,
                        "words": ocr["words"],
                        "avg_confidence": ocr.get("avg_confidence"),
                    }
                )

    if ocr_notes:
        prepared_task = (
            prepared_task.rstrip()
            + "\n\nOCR context:\n"
            + "\n".join(f"- {note}" for note in ocr_notes)
        )

    return (
        prepared_task,
        image_paths,
        ocr_notes,
        capture_meta,
        active_window,
        capture_target,
        is_ocr_only,
    )


def _is_ocr_only_task(task: str) -> bool:
    """Check if task is OCR-only (no visual reasoning needed).

    Phase 2C: Specialist Routing
    Route OCR-only tasks to OCR engine, visual reasoning to vision model.
    """
    lowered = task.lower()
    return any(hint in lowered for hint in _OCR_ONLY_HINTS)


def _extract_image_paths(task: str) -> list[str]:
    paths: list[str] = []
    for candidate in extract_candidate_paths(task):
        resolved = resolve_workspace_path(candidate)
        if resolved is None or not resolved.is_file():
            continue
        if resolved.suffix.lower() not in {
            ".bmp",
            ".gif",
            ".jpeg",
            ".jpg",
            ".png",
            ".webp",
        }:
            continue
        normalized = str(resolved)
        if normalized not in paths:
            paths.append(normalized)
    return paths


def _needs_screen_capture(task: str) -> bool:
    lowered = task.lower()
    hints = ("screen", "screenshot", "capture", "ocr", "window", "image on screen")
    return any(hint in lowered for hint in hints)


def _capture_target_for_task(task: str) -> str:
    lowered = task.lower()
    whole_screen_hints = ("whole screen", "full screen", "entire screen", "desktop")
    if any(hint in lowered for hint in whole_screen_hints):
        return "screen"

    foreground_window_hints = (
        "active window",
        "current window",
        "this window",
        "dialog",
        "window",
    )
    if any(hint in lowered for hint in foreground_window_hints):
        return "foreground_window"
    return "screen"


def _normalize_active_window(payload: dict | None) -> dict | None:
    if not payload or not payload.get("ok"):
        return None

    normalized = {
        "window_title": str(payload.get("window_title", "")).strip() or None,
        "process_name": str(payload.get("process_name", "")).strip() or None,
    }
    if payload.get("pid") is not None:
        normalized["pid"] = payload.get("pid")

    if not normalized.get("window_title") and not normalized.get("process_name"):
        return None
    return normalized

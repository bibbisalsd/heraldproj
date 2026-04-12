from __future__ import annotations

from .ocr_read import read as ocr_read
from .screen_capture import capture


def analyze_screen(temp_image_path: str, *, capture_target: str = "screen") -> dict:
    shot = capture(temp_image_path, target=capture_target)
    if not shot["ok"]:
        return {
            "ok": False,
            "reason": shot.get("reason", "capture_failed"),
            "capture_mode": shot.get("mode", ""),
            "capture_target": shot.get("target", capture_target),
            "image_path": shot.get("path", temp_image_path),
            "text": "",
        }

    image_path = str(shot.get("path", temp_image_path))
    ocr = ocr_read(image_path)
    if not ocr.get("ok"):
        return {
            "ok": False,
            "reason": ocr.get("reason", "ocr_failed"),
            "capture_mode": shot.get("mode", ""),
            "capture_target": shot.get("target", capture_target),
            "ocr_mode": ocr.get("mode", ""),
            "image_path": image_path,
            "text": "",
        }

    text = str(ocr.get("text", ""))
    if not text.strip():
        return {
            "ok": False,
            "reason": "ocr_text_unavailable",
            "capture_mode": shot.get("mode", ""),
            "capture_target": shot.get("target", capture_target),
            "ocr_mode": ocr.get("mode", ""),
            "image_path": image_path,
            "text": "",
        }

    return {
        "ok": True,
        "text": text,
        "capture_mode": shot.get("mode", ""),
        "capture_target": shot.get("target", capture_target),
        "ocr_mode": ocr.get("mode", ""),
        "image_path": image_path,
        "ocr_backend": ocr.get("backend", ""),
        "analysis_mode": f"ocr_{ocr.get('mode', 'unknown')}",
    }

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from jarvis.models.workspace_inputs import resolve_workspace_path


def read(
    image_path: str, include_confidence: bool = False, include_boxes: bool = False
) -> dict:
    """Read text from image with optional confidence scores and bounding boxes.

    Phase 2C: Vision Depth
    - OCR confidence scores (per-word when available)
    - Bounding box output (x, y, w, h for each word/line)

    Args:
        image_path: Path to image file
        include_confidence: Include per-word confidence scores
        include_boxes: Include bounding box coordinates

    Returns: dict with ok, text, and optionally:
        - words: list of {text, confidence, box: [x,y,w,h]}
        - lines: list of {text, confidence, box: [x,y,w,h]}
        - avg_confidence: Average confidence score
    """
    resolved = resolve_workspace_path(image_path)
    if resolved is None:
        return {
            "ok": False,
            "image_path": image_path,
            "text": "",
            "reason": "image_not_found",
        }

    sidecar = _read_sidecar(resolved)
    if sidecar is not None:
        return sidecar

    windows_result = _read_windows_ocr(resolved, include_confidence, include_boxes)
    if windows_result.get("ok") and str(windows_result.get("text", "")).strip():
        return windows_result

    tesseract_result = _read_tesseract_cli(resolved, include_confidence, include_boxes)
    if tesseract_result.get("ok") and str(tesseract_result.get("text", "")).strip():
        return tesseract_result

    if windows_result.get("available"):
        return windows_result

    if tesseract_result.get("available"):
        return tesseract_result

    return {
        "ok": True,
        "image_path": str(resolved),
        "text": "",
        "mode": "none",
        "backend": "none",
        "reason": "ocr_backend_unavailable",
    }


def _read_sidecar(resolved: Path) -> dict | None:
    candidates = [
        Path(str(resolved) + ".ocr.txt"),
        resolved.with_suffix(".ocr.txt"),
        resolved.with_suffix(".txt"),
    ]
    for candidate in candidates:
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            return {
                "ok": True,
                "image_path": str(resolved),
                "text": text,
                "mode": "sidecar",
                "backend": "sidecar_override",
                "sidecar_path": str(candidate),
            }
    return None


def _read_windows_ocr(
    resolved: Path, include_confidence: bool = False, include_boxes: bool = False
) -> dict:
    """Read OCR with optional confidence scores and bounding boxes.

    Phase 2C: Vision Depth - Windows Media OCR
    """
    if os.name != "nt":
        return {"ok": False, "available": False, "reason": "windows_only"}

    path_literal = str(resolved).replace("'", "''")

    # Build PowerShell script with optional confidence/boxes output
    boxes_logic = ""
    if include_boxes:
        boxes_logic = """
    $words = @()
    foreach ($line in $result.Lines) {
        foreach ($word in $line.Words) {
            $box = $word.BoundingRect
            $words += @{
                text = $word.Text
                confidence = 1.0  # Windows OCR doesn't expose per-word confidence
                box = @{ x = [int]$box.X; y = [int]$box.Y; w = [int]$box.Width; h = [int]$box.Height }
            }
        }
    }
"""
    confidence_logic = ""
    if include_confidence or include_boxes:
        confidence_logic = """, words = $words"""

    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod }} | Select-Object -First 1
function Await([object]$op, [Type]$type) {{
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait()
    return $task.Result
}}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{path_literal}')) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {{
    throw 'windows_ocr_engine_unavailable'
}}
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
{boxes_logic}
@{{ ok = $true; available = $true; text = [string]$result.Text; backend = 'windows_media_ocr'; mode = 'windows_ocr'{confidence_logic} }} | ConvertTo-Json -Depth 10 -Compress
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "reason": f"windows_ocr_runner_failed:{type(exc).__name__}",
        }

    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    payload_text = lines[-1] if lines else ""
    if payload_text:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            payload.setdefault("available", True)
            # Calculate average confidence if words provided
            if include_confidence and "words" in payload:
                words = payload.get("words", [])
                if words:
                    avg_conf = sum(w.get("confidence", 0) for w in words) / len(words)
                    payload["avg_confidence"] = round(avg_conf, 3)
            return payload

    stderr = completed.stderr.strip()
    reason = stderr.splitlines()[-1].strip() if stderr else "windows_ocr_failed"
    return {"ok": False, "available": completed.returncode == 0, "reason": reason}


def _read_tesseract_cli(
    resolved: Path, include_confidence: bool = False, include_boxes: bool = False
) -> dict:
    """Read OCR with Tesseract with optional confidence and boxes.

    Phase 2C: Vision Depth - Tesseract OCR
    Uses TSV output format for word-level confidence and bounding boxes.
    """
    tesseract_bin = shutil.which("tesseract")
    if not tesseract_bin:
        return {"ok": False, "available": False, "reason": "tesseract_not_installed"}

    # Use TSV output for word-level data
    output_flag = "tsv" if (include_confidence or include_boxes) else "stdout"
    psm = "6"  # Assume a single uniform block of text

    try:
        completed = subprocess.run(
            [
                tesseract_bin,
                str(resolved),
                "stdout",
                "--psm",
                psm,
                "-c",
                "tessedit_create_tsv=1",
            ]
            if output_flag == "tsv"
            else [tesseract_bin, str(resolved), "stdout", "--psm", psm],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "available": True,
            "reason": f"tesseract_failed:{type(exc).__name__}",
        }

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        reason = stderr.splitlines()[-1].strip() if stderr else "tesseract_failed"
        return {"ok": False, "available": True, "reason": reason}

    if output_flag == "tsv":
        # Parse TSV output
        return _parse_tesseract_tsv(completed.stdout, include_confidence, include_boxes)

    return {
        "ok": True,
        "available": True,
        "text": completed.stdout,
        "backend": "tesseract_cli",
        "mode": "tesseract",
    }


def _parse_tesseract_tsv(
    tsv_output: str, include_confidence: bool, include_boxes: bool
) -> dict:
    """Parse Tesseract TSV output into structured format.

    TSV format: level  page_num  block_num  par_num  line_num  word_num  left  top  width  height  conf  text
    """
    lines = tsv_output.strip().split("\n")
    if len(lines) < 2:
        return {
            "ok": True,
            "text": "",
            "backend": "tesseract_cli",
            "mode": "tesseract",
            "words": [],
        }

    words = []
    full_text_parts = []

    for line in lines[1:]:  # Skip header
        parts = line.split("\t")
        if len(parts) < 12:
            continue

        try:
            _ = int(parts[5])  # word_num (unused)
            left = int(parts[6])
            top = int(parts[7])
            width = int(parts[8])
            height = int(parts[9])
            conf = int(parts[10]) if parts[10].isdigit() else -1
            text = parts[11].strip()

            if not text:
                continue

            full_text_parts.append(text)

            word_entry = {"text": text}
            if include_confidence and conf >= 0:
                word_entry["confidence"] = conf / 100.0  # Tesseract confidence is 0-100
            if include_boxes:
                word_entry["box"] = {"x": left, "y": top, "w": width, "h": height}

            words.append(word_entry)
        except (ValueError, IndexError):
            continue

    result = {
        "ok": True,
        "text": " ".join(full_text_parts),
        "backend": "tesseract_cli",
        "mode": "tesseract",
    }

    if include_confidence or include_boxes:
        result["words"] = words
        if words and include_confidence:
            conf_values = [
                w.get("confidence", 0) for w in words if w.get("confidence", 0) >= 0
            ]
            if conf_values:
                result["avg_confidence"] = round(sum(conf_values) / len(conf_values), 3)

    return result

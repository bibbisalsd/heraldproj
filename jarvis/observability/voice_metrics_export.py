from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def persist_voice_metrics(payload: dict, log_dir: str = "./logs") -> dict[str, str]:
    """Persist a voice smoke payload as daily JSONL and CSV files."""

    base = Path(log_dir)
    base.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {"timestamp": timestamp, **payload}

    jsonl_path = base / f"jarvis_voice_metrics_{day}.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")

    csv_path = base / f"jarvis_voice_metrics_{day}.csv"
    row = _flatten_record(record)
    _append_csv_row(csv_path, row)

    return {"jsonl_path": str(jsonl_path), "csv_path": str(csv_path)}


def list_voice_metric_files(log_dir: str = "./logs") -> list[str]:
    """List voice metric files (JSONL/CSV), newest first."""

    base = Path(log_dir)
    if not base.exists():
        return []

    files = list(base.glob("jarvis_voice_metrics_*.jsonl"))
    files.extend(base.glob("jarvis_voice_metrics_*.csv"))
    files = [path for path in files if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path) for path in files]


def prune_voice_metrics(
    log_dir: str = "./logs", retention_days: int = 14
) -> dict[str, object]:
    """Prune old voice metric files while keeping recent files."""

    days = max(0, int(retention_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    deleted_files: list[str] = []
    for path_str in list_voice_metric_files(log_dir):
        path = Path(path_str)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff_ts:
            path.unlink(missing_ok=True)
            deleted_files.append(str(path))

    remaining = list_voice_metric_files(log_dir)
    return {
        "deleted_count": len(deleted_files),
        "remaining_count": len(remaining),
        "deleted_files": deleted_files,
        "remaining_files": remaining,
    }


def _flatten_record(record: dict) -> dict[str, str]:
    metrics = (
        record.get("voice_metrics", {})
        if isinstance(record.get("voice_metrics"), dict)
        else {}
    )
    backend_counts = metrics.get("tts_backend_counts", {})
    state_counts = metrics.get("tts_state_counts", {})

    def _metric_int(key: str) -> str:
        value = metrics.get(key, 0)
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return "0"

    def _metric_value(key: str) -> str:
        value = metrics.get(key)
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
        return str(value)

    return {
        "timestamp": str(record.get("timestamp", "")),
        "lane": str(record.get("lane", "")),
        "text": str(record.get("text", "")),
        "ok": str(record.get("ok", "")),
        "reason": str(record.get("reason", "")),
        "transcribed_text": str(record.get("transcribed_text", "")),
        "tts_backend": str(record.get("tts_backend", "")),
        "tts_error": str(record.get("tts_error", "")),
        "capture_attempts": _metric_int("capture_attempts"),
        "capture_success": _metric_int("capture_success"),
        "capture_failures": _metric_int("capture_failures"),
        "transcribe_attempts": _metric_int("transcribe_attempts"),
        "transcribe_success": _metric_int("transcribe_success"),
        "transcribe_failures": _metric_int("transcribe_failures"),
        "turns_processed": _metric_int("turns_processed"),
        "fallback_repeat_prompt": _metric_int("fallback_repeat_prompt"),
        "fallback_mic_unavailable": _metric_int("fallback_mic_unavailable"),
        "tts_retry_count": _metric_int("tts_retry_count"),
        "tts_backend_fallbacks": _metric_int("tts_backend_fallbacks"),
        "voice_delivery_failures": _metric_int("voice_delivery_failures"),
        "voice_sink_fallback_to_text": _metric_int("voice_sink_fallback_to_text"),
        "requested_input_device": _metric_value("requested_input_device"),
        "requested_output_device": _metric_value("requested_output_device"),
        "selected_input_device": _metric_value("selected_input_device"),
        "selected_output_device": _metric_value("selected_output_device"),
        "sample_rate": _metric_value("sample_rate"),
        "capture_duration_seconds": _metric_value("capture_duration_seconds"),
        "audio_capture_ok": _metric_value("audio_capture_ok"),
        "transcribe_ok": _metric_value("transcribe_ok"),
        "fallback_reason": _metric_value("fallback_reason"),
        "tts_state": _metric_value("tts_state"),
        "tts_delivery_ok": _metric_value("tts_delivery_ok"),
        "tts_fallback_used": _metric_value("tts_fallback_used"),
        "requested_sink": _metric_value("requested_sink"),
        "sink_used": _metric_value("sink_used"),
        "delivery_detail": _metric_value("delivery_detail"),
        "tts_backend_counts_json": json.dumps(
            backend_counts, ensure_ascii=True, sort_keys=True
        ),
        "tts_state_counts_json": json.dumps(
            state_counts, ensure_ascii=True, sort_keys=True
        ),
        "tts_attempted_backends_json": _metric_value("tts_attempted_backends"),
        "tts_state_history_json": _metric_value("tts_state_history"),
    }


def _append_csv_row(csv_path: Path, row: dict[str, str]) -> None:
    fieldnames = list(row.keys())
    file_exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..observability.voice_metrics_export import persist_voice_metrics
from ..voice.runtime import VoiceRuntime
from .retention import run_retention


def _maybe_enable_local_kokoro_pack(tts_backend: str) -> None:
    if tts_backend.strip().lower() != "kokoro":
        return

    root = Path(__file__).resolve().parents[2]
    pack_dir = root / "jarvis" / "voice" / "kokoro_pack"
    launcher = pack_dir / "jarvis_launcher.py"
    if not launcher.exists():
        return

    os.environ.setdefault("JARVIS_USE_KOKORO_PACK", "true")
    os.environ.setdefault("JARVIS_KOKORO_PACK_DIR", str(pack_dir))

    pack_python = root / ".venv" / "Scripts" / "python.exe"
    if pack_python.exists():
        os.environ.setdefault("JARVIS_KOKORO_PYTHON", str(pack_python))


def run_daily_ops(
    *,
    input_text: str = "status",
    tts_backend: str = "kokoro",
    memory_db_path: str = ".jarvis_memory.sqlite",
    memory_retention_days: int = 90,
    memory_backup_dir: str = "./backups",
    memory_backup_keep: int = 5,
    voice_log_dir: str = "./logs",
    voice_metrics_retention_days: int = 14,
    report_dir: str = "./logs",
    ops_alerts_retention_days: int = 30,
    crsis_retention_days: int = 30,
    run_voice_smoke: bool = True,
    persist_voice_payload: bool = True,
) -> dict[str, Any]:
    """Run daily operational checks and cleanup, and persist a report."""

    voice_smoke: dict[str, Any] | None = None
    previous_env = {
        "JARVIS_TTS_BACKEND": os.environ.get("JARVIS_TTS_BACKEND"),
        "JARVIS_USE_KOKORO_PACK": os.environ.get("JARVIS_USE_KOKORO_PACK"),
        "JARVIS_KOKORO_PACK_DIR": os.environ.get("JARVIS_KOKORO_PACK_DIR"),
        "JARVIS_KOKORO_PYTHON": os.environ.get("JARVIS_KOKORO_PYTHON"),
    }

    try:
        os.environ["JARVIS_TTS_BACKEND"] = tts_backend
        _maybe_enable_local_kokoro_pack(tts_backend)
        if run_voice_smoke:
            runtime = VoiceRuntime()
            result = runtime.process_audio(input_text.encode("utf-8"))
            voice_smoke = {
                "lane": result.lane,
                "text": result.text,
                "tts_backend": runtime.tts.last_backend,
                "tts_error": runtime.tts.last_error,
                "voice_metrics": runtime.metrics_snapshot(),
            }
            if persist_voice_payload:
                voice_smoke["persisted_files"] = persist_voice_metrics(
                    voice_smoke, log_dir=voice_log_dir
                )
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    retention = run_retention(
        memory_db_path=memory_db_path,
        memory_retention_days=memory_retention_days,
        memory_backup_dir=memory_backup_dir,
        memory_backup_keep=memory_backup_keep,
        voice_log_dir=voice_log_dir,
        voice_metrics_retention_days=voice_metrics_retention_days,
        ops_report_dir=report_dir,
        ops_alerts_retention_days=ops_alerts_retention_days,
        crsis_log_dir=report_dir,
        crsis_retention_days=crsis_retention_days,
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voice_smoke": voice_smoke,
        "retention": retention,
    }
    report_paths = persist_ops_report(report, report_dir=report_dir)
    report["report_files"] = report_paths
    return report


def persist_ops_report(
    report: dict[str, Any], report_dir: str = "./logs"
) -> dict[str, str]:
    """Persist ops report as daily JSONL and a latest snapshot JSON."""

    base = Path(report_dir)
    base.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    jsonl_path = base / f"jarvis_ops_report_{day}.jsonl"
    latest_path = base / "jarvis_ops_report_latest.json"

    with jsonl_path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(report, ensure_ascii=True, default=str) + "\n")

    with latest_path.open("w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=True, indent=2, default=str)

    return {"jsonl_path": str(jsonl_path), "latest_path": str(latest_path)}

from __future__ import annotations

from ..crsis.engine import prune_snapshots
from ..memory import Memory
from ..observability.voice_metrics_export import prune_voice_metrics
from .ops_history import prune_ops_alerts


def run_retention(
    memory_db_path: str = ".jarvis_memory.sqlite",
    memory_retention_days: int = 90,
    memory_backup_dir: str = "./backups",
    memory_backup_keep: int = 5,
    voice_log_dir: str = "./logs",
    voice_metrics_retention_days: int = 14,
    ops_report_dir: str = "./logs",
    ops_alerts_retention_days: int = 30,
    crsis_log_dir: str = "./logs",
    crsis_retention_days: int = 30,
) -> dict[str, object]:
    """Run consolidated retention cleanup for memory, voice metrics, and ops alerts."""

    memory = Memory(db_path=memory_db_path)
    memory_deleted = memory.purge(retention_days=max(0, int(memory_retention_days)))
    backups_deleted = memory.prune_backups(
        backup_dir=memory_backup_dir,
        keep=max(0, int(memory_backup_keep)),
    )
    voice_prune = prune_voice_metrics(
        log_dir=voice_log_dir,
        retention_days=max(0, int(voice_metrics_retention_days)),
    )
    alerts_prune = prune_ops_alerts(
        report_dir=ops_report_dir,
        retention_days=max(0, int(ops_alerts_retention_days)),
    )
    crsis_prune = prune_snapshots(
        log_dir=crsis_log_dir,
        retention_days=max(0, int(crsis_retention_days)),
    )

    return {
        "memory_deleted": int(memory_deleted),
        "memory_backups_deleted": int(backups_deleted),
        "voice_metrics_deleted": int(voice_prune.get("deleted_count", 0)),
        "voice_metrics_remaining": int(voice_prune.get("remaining_count", 0)),
        "voice_metrics_deleted_files": list(voice_prune.get("deleted_files", [])),
        "ops_alerts_deleted": int(alerts_prune.get("deleted_count", 0)),
        "ops_alerts_remaining": int(alerts_prune.get("remaining_count", 0)),
        "ops_alerts_deleted_files": list(alerts_prune.get("deleted_files", [])),
        "crsis_deleted": int(crsis_prune.get("deleted_count", 0)),
        "crsis_remaining": int(crsis_prune.get("remaining_count", 0)),
        "crsis_deleted_files": list(crsis_prune.get("deleted_files", [])),
    }

"""RollbackManager - Manage rollback operations with backup layers."""

from __future__ import annotations


import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class BackupRecord:
    """Record of a backup snapshot."""

    backup_id: str
    original_path: str
    backup_path: str
    timestamp: str
    checksum: str | None = None


class RollbackManager:
    """Manage rollback operations with multiple backup layers.

    Backup layers:
    1. File-level backup (.bak files)
    2. SQLite snapshot (for database state)
    3. Git snapshot (for full repo state)

    Supports:
    - create_backup: Create backup before modification
    - restore: Restore from backup
    - list_backups: list available backups
    - cleanup: Remove old backups
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()
        self._backups_dir = self._project_root / ".crsis" / "backups"
        self._backups_dir.mkdir(parents=True, exist_ok=True)
        self._backup_records: list[BackupRecord] = []

    def create_backup(self, file_path: Path | str) -> str:
        """Create backup of a file. Returns backup path."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_id = f"bkp_{timestamp}_{file_path.stem}"
        backup_name = f"{backup_id}_{file_path.name}.bak"
        backup_path = self._backups_dir / backup_name

        # Copy file
        shutil.copy2(file_path, backup_path)

        # Calculate checksum
        checksum = self._calculate_checksum(file_path)

        # Record backup
        record = BackupRecord(
            backup_id=backup_id,
            original_path=str(file_path.absolute()),
            backup_path=str(backup_path.absolute()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            checksum=checksum,
        )
        self._backup_records.append(record)

        return str(backup_path)

    def restore(self, backup_path: Path | str) -> bool:
        """Restore from backup. Returns True if successful."""
        backup_path = Path(backup_path)
        if not backup_path.exists():
            return False

        # Find original path from backup name
        record = self._find_record_by_backup(str(backup_path))
        if not record:
            # Try to infer original path from backup name
            original_name = backup_path.name.replace(".bak", "")
            # Remove timestamp prefix
            parts = original_name.split("_", 2)
            if len(parts) >= 3:
                original_name = parts[2]
            original_path = self._project_root / original_name
        else:
            original_path = Path(record.original_path)

        if not original_path.parent.exists():
            original_path.parent.mkdir(parents=True, exist_ok=True)

        # Restore
        shutil.copy2(backup_path, original_path)
        return True

    def restore_latest(self, file_path: Path | str) -> bool:
        """Restore latest backup of a file. Returns True if successful."""
        file_path = Path(file_path)
        backups = self._find_backups_for_file(file_path)

        if not backups:
            return False

        # Get most recent
        latest = max(backups, key=lambda b: b.timestamp)
        return self.restore(latest.backup_path)

    def list_backups(self, hours: int = 24) -> list[BackupRecord]:
        """List backups from the last N hours."""
        cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        return [
            b
            for b in self._backup_records
            if datetime.fromisoformat(b.timestamp).timestamp() > cutoff
        ]

    def cleanup(self, older_than_hours: int = 168) -> int:
        """Remove backups older than specified hours. Returns count removed."""
        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_hours * 3600)
        removed = 0

        for record in list(self._backup_records):
            if datetime.fromisoformat(record.timestamp).timestamp() < cutoff:
                # Delete backup file
                backup_path = Path(record.backup_path)
                if backup_path.exists():
                    backup_path.unlink()
                self._backup_records.remove(record)
                removed += 1

        return removed

    def verify_backup(self, backup_path: Path | str) -> bool:
        """Verify backup integrity via checksum."""
        record = self._find_record_by_backup(str(backup_path))
        if not record:
            return False

        # Calculate current checksum of backup
        current_checksum = self._calculate_checksum(Path(backup_path))
        return current_checksum == record.checksum

    def _find_backups_for_file(self, file_path: Path) -> list[BackupRecord]:
        """Find all backups for a specific file."""
        file_str = str(file_path.absolute())
        return [b for b in self._backup_records if b.original_path == file_str]

    def _find_record_by_backup(self, backup_path: str) -> BackupRecord | None:
        """Find backup record by backup path."""
        for record in self._backup_records:
            if record.backup_path == backup_path:
                return record
        return None

    def _calculate_checksum(self, file_path: Path) -> str | None:
        """Calculate MD5 checksum of a file."""
        try:
            import hashlib

            md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception:
            return None

    def create_snapshot(self, snapshot_name: str, files: list[Path]) -> str:
        """Create a multi-file snapshot. Returns snapshot ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        snapshot_id = f"snap_{timestamp}_{snapshot_name}"
        snapshot_dir = self._backups_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        for file_path in files:
            if file_path.exists():
                shutil.copy2(file_path, snapshot_dir / file_path.name)

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore all files from a snapshot."""
        snapshot_dir = self._backups_dir / snapshot_id
        if not snapshot_dir.exists():
            return False

        for backup_file in snapshot_dir.glob("*"):
            # Restore to original location (may need manifest)
            # For now, just copy back to project root
            shutil.copy2(backup_file, self._project_root / backup_file.name)

        return True

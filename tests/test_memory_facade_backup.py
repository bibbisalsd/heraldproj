from __future__ import annotations
from pathlib import Path

from jarvis.memory import Memory


def test_memory_facade_backup_and_list(tmp_path):
    db_path = str(tmp_path / "memory.sqlite")
    backup_dir = str(tmp_path / "backups")
    mem = Memory(db_path=db_path)
    mem.remember("user_name", "Alex", confidence=0.95)

    backup_file = mem.backup(backup_dir=backup_dir)
    assert Path(backup_file).exists()

    backups = mem.list_backups(backup_dir=backup_dir)
    assert backups
    assert backup_file in backups


def test_memory_facade_restore_missing_returns_false(tmp_path):
    db_path = str(tmp_path / "memory.sqlite")
    mem = Memory(db_path=db_path)
    assert mem.restore(str(tmp_path / "missing.sqlite")) is False


def test_memory_facade_prune_backups(tmp_path):
    db_path = str(tmp_path / "memory.sqlite")
    backup_dir = str(tmp_path / "backups")
    mem = Memory(db_path=db_path)
    mem.remember("k", "v", confidence=0.95)

    for _ in range(3):
        mem.backup(backup_dir=backup_dir)

    deleted = mem.prune_backups(backup_dir=backup_dir, keep=1)
    assert deleted >= 1
    assert len(mem.list_backups(backup_dir=backup_dir)) == 1

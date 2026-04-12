from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from jarvis.brain_core.memory_service import MemoryService


@pytest.fixture
def mem_svc(tmp_path: Path) -> MemoryService:
    db_path = str(tmp_path / "test_memory.sqlite")
    return MemoryService(db_path)


@pytest.fixture
def backup_dir(tmp_path: Path) -> str:
    return str(tmp_path / "test_backups")


def test_backup_creates_file(mem_svc: MemoryService, backup_dir: str) -> None:
    mem_svc.save("city", "London", 0.9)
    backup_path = mem_svc.backup(backup_dir)
    assert Path(backup_path).exists()


def test_backup_contains_data(mem_svc: MemoryService, backup_dir: str) -> None:
    mem_svc.save("k1", "v1", 0.9)
    mem_svc.save("k2", "v2", 0.95)
    backup_path = mem_svc.backup(backup_dir)

    with sqlite3.connect(backup_path) as conn:
        rows = conn.execute("SELECT key, value FROM memory_facts ORDER BY id").fetchall()
    assert rows == [("k1", "v1"), ("k2", "v2")]


def test_restore_recovers_data(mem_svc: MemoryService, backup_dir: str) -> None:
    mem_svc.save("name", "Alex", 0.9)
    backup_path = mem_svc.backup(backup_dir)

    with sqlite3.connect(mem_svc.db_path) as conn:
        conn.execute("DELETE FROM memory_facts")
        conn.commit()
    assert mem_svc.retrieve("name") == []

    assert mem_svc.restore(backup_path) is True
    rows = mem_svc.retrieve("name")
    assert len(rows) == 1
    assert rows[0].value == "Alex"


def test_restore_nonexistent_returns_false(mem_svc: MemoryService) -> None:
    assert mem_svc.restore("does_not_exist.sqlite") is False


def test_list_backups_order(mem_svc: MemoryService, backup_dir: str) -> None:
    mem_svc.save("k", "v", 0.9)
    backups = [mem_svc.backup(backup_dir), mem_svc.backup(backup_dir), mem_svc.backup(backup_dir)]
    base_time = 1_700_000_000
    for index, path in enumerate(backups):
        os.utime(path, (base_time + index, base_time + index))

    listed = mem_svc.list_backups(backup_dir)
    assert listed[0] == backups[2]
    assert listed[1] == backups[1]
    assert listed[2] == backups[0]


def test_list_backups_empty_dir(mem_svc: MemoryService, tmp_path: Path) -> None:
    assert mem_svc.list_backups(str(tmp_path / "missing")) == []


def test_prune_backups_keeps_recent(mem_svc: MemoryService, backup_dir: str) -> None:
    mem_svc.save("k", "v", 0.9)
    created = [mem_svc.backup(backup_dir) for _ in range(5)]
    base_time = 1_700_000_000
    for index, path in enumerate(created):
        os.utime(path, (base_time + index, base_time + index))

    deleted = mem_svc.prune_backups(backup_dir=backup_dir, keep=2)

    assert deleted == 3
    remaining = mem_svc.list_backups(backup_dir)
    assert len(remaining) == 2
    assert remaining == [created[4], created[3]]


def test_backup_dir_auto_created(mem_svc: MemoryService, tmp_path: Path) -> None:
    missing_dir = tmp_path / "new" / "nested" / "backups"
    backup_path = mem_svc.backup(str(missing_dir))

    assert missing_dir.exists()
    assert Path(backup_path).exists()

from __future__ import annotations
from jarvis.memory import Memory


def test_retention_purge_keeps_new_records(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    assert memory.remember("fact", "value", 0.9) is True
    deleted = memory.purge(retention_days=1)
    assert isinstance(deleted, int)
    assert len(memory.recall("fact")) >= 1

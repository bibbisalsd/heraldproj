from __future__ import annotations
from jarvis.memory import Memory


def test_memory_write_policy_only_accepts_stable_facts(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    assert memory.remember("city", "London", 0.80) is True
    assert memory.remember("guess", "Maybe rain", 0.60) is False
    rows = memory.recall("city")
    assert len(rows) == 1
    assert rows[0].value == "London"


def test_memory_respects_env_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "env_memory.sqlite"
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(db_path))

    memory = Memory()
    memory.remember("city", "London", 0.95)

    assert db_path.exists()
    assert memory.recall("city")[0].value == "London"


def test_memory_singleton_name_keeps_latest_value(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    assert memory.remember_latest("user_name", "Sam", confidence=0.95) is True
    assert memory.remember_latest("user_name", "James", confidence=0.95) is True

    rows = memory.recall("user_name")
    assert len(rows) == 1
    assert rows[0].value == "James"

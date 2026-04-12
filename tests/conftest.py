from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("JARVIS_ENABLE_EMBEDDING_MATCH", "false")
os.environ.setdefault("JARVIS_ENABLE_SEMANTIC_MEMORY_RETRIEVAL", "false")


@pytest.fixture(autouse=True)
def isolated_memory_db(monkeypatch, tmp_path):
    memory_db = tmp_path / "test_memory.sqlite"
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(memory_db))
    yield

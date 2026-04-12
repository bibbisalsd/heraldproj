from __future__ import annotations
import sqlite3

from jarvis.memory import Memory


def test_memory_schema_contains_required_columns(tmp_path):
    db_path = tmp_path / "memory.sqlite"
    Memory(db_path=str(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(memory_facts)").fetchall()
        embedding_rows = conn.execute("PRAGMA table_info(memory_embeddings)").fetchall()
    finally:
        conn.close()
    columns = {row[1] for row in rows}
    embedding_columns = {row[1] for row in embedding_rows}
    assert {"id", "key", "value", "confidence", "created_at"} <= columns
    assert {"memory_id", "model", "vector_json", "created_at"} <= embedding_columns

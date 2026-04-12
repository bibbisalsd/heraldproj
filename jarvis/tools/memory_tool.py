from __future__ import annotations

from jarvis.memory import Memory
from jarvis.brain_core.memory_service import MemoryService


def save(
    memory: Memory, category: str, content: str, metadata: dict | None = None
) -> dict:
    metadata = metadata or {}
    confidence = float(metadata.get("confidence", 0.8))
    ok = memory.remember(category, content, confidence)
    return {"ok": ok, "category": category}


def retrieve(memory: Memory, query: str, top_k: int = 6) -> dict:
    rows = memory.search(query, top_k=top_k)
    return {
        "items": [row.value for row in rows],
        "count": len(rows),
        "matches": [
            {
                "key": row.key,
                "value": row.value,
                "match_type": row.match_type,
                "score": round(float(row.score), 4),
            }
            for row in rows
        ],
    }


# =============================================================================
# Phase 3C: Memory Productization - Operator CLI Commands
# =============================================================================


def inspect(memory_service: MemoryService, key: str) -> dict:
    """Inspect a memory by key.

    Returns the memory record with full metadata including provenance.
    """
    records = memory_service.retrieve(key)
    if not records:
        return {"ok": False, "reason": "memory_not_found", "key": key}

    return {
        "ok": True,
        "key": key,
        "count": len(records),
        "records": [
            {
                "id": rec.id,
                "value": rec.value,
                "confidence": rec.confidence,
                "created_at": rec.created_at,
                "source": rec.source,
                "source_id": rec.source_id,
                "utterance": rec.utterance,
            }
            for rec in records
        ],
    }


def list_memories(
    memory_service: MemoryService, query: str | None = None, limit: int = 20
) -> dict:
    """List memories, optionally filtered by search query.

    Returns a list of memory records with their metadata.
    """
    if query:
        rows = memory_service.search(query, top_k=limit)
    else:
        # List all memories (no query) - retrieve from DB directly
        import sqlite3

        try:
            conn = sqlite3.connect(memory_service.db_path)
            rows_raw = conn.execute(
                "SELECT id, key, value, confidence, created_at, source, source_id, utterance FROM memory_facts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            from jarvis.brain_core.memory_service import MemoryRecord

            rows = [
                MemoryRecord(
                    id=row[0],
                    key=row[1],
                    value=row[2],
                    confidence=row[3],
                    created_at=row[4],
                    source=row[5],
                    source_id=row[6],
                    utterance=row[7],
                )
                for row in rows_raw
            ]
        except Exception as e:
            return {"ok": False, "reason": f"list_failed: {type(e).__name__}: {e}"}

    return {
        "ok": True,
        "count": len(rows),
        "memories": [
            {
                "id": rec.id,
                "key": rec.key,
                "value": rec.value,
                "confidence": rec.confidence,
                "created_at": rec.created_at,
                "match_type": getattr(rec, "match_type", "exact"),
                "score": round(float(getattr(rec, "score", 1.0)), 4),
            }
            for rec in rows
        ],
    }


def edit(
    memory_service: MemoryService, key: str, new_value: str, confidence: float = 0.95
) -> dict:
    """Edit/Update a memory value.

    Uses force_save to bypass contradiction guard for intentional updates.
    """
    ok = memory_service.force_save(key, new_value, confidence)
    if not ok:
        return {"ok": False, "reason": "update_failed", "key": key}
    return {"ok": True, "key": key, "value": new_value}


def forget(memory_service: MemoryService, key: str) -> dict:
    """Forget/Delete a memory by key.

    Removes all records for the given key.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(memory_service.db_path)
        cursor = conn.execute("DELETE FROM memory_facts WHERE key = ?", (key,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return {"ok": deleted > 0, "deleted_count": int(deleted), "key": key}
    except Exception as e:
        return {"ok": False, "reason": f"delete_failed: {type(e).__name__}: {e}"}


def backup(memory_service: MemoryService, backup_dir: str = "./backups") -> dict:
    """Create a memory backup."""
    try:
        path = memory_service.backup(backup_dir)
        return {"ok": True, "backup_path": path}
    except Exception as e:
        return {"ok": False, "reason": f"backup_failed: {type(e).__name__}: {e}"}


def restore(memory_service: MemoryService, backup_path: str) -> dict:
    """Restore memory from a backup file."""
    ok = memory_service.restore(backup_path)
    if not ok:
        return {
            "ok": False,
            "reason": "restore_failed_backup_not_found",
            "backup_path": backup_path,
        }
    return {"ok": True, "restored_from": backup_path}


def list_backups(memory_service: MemoryService, backup_dir: str = "./backups") -> dict:
    """List available memory backups."""
    backups = memory_service.list_backups(backup_dir)
    return {
        "ok": True,
        "count": len(backups),
        "backups": backups,
    }


# =============================================================================
# Phase 3C: Memory Productization - Granular ID-Based Operations
# =============================================================================


def inspect_by_id(memory_service: MemoryService, memory_id: int) -> dict:
    """Inspect a single memory record by its stable row ID.

    Enables intent commands like 'inspect memory #42'.
    """
    record = memory_service.get_by_id(memory_id)
    if record is None:
        return {"ok": False, "reason": "memory_not_found", "id": memory_id}

    return {
        "ok": True,
        "id": memory_id,
        "record": {
            "id": record.id,
            "key": record.key,
            "value": record.value,
            "confidence": record.confidence,
            "created_at": record.created_at,
            "source": record.source,
            "source_id": record.source_id,
            "utterance": record.utterance,
        },
    }


def forget_by_id(memory_service: MemoryService, memory_id: int) -> dict:
    """Forget/Delete a single memory record by its stable row ID.

    Enables intent commands like 'forget #42'.
    """
    deleted = memory_service.forget_by_id(memory_id)
    return {
        "ok": deleted,
        "id": memory_id,
        "deleted": deleted,
    }


def update_by_id(
    memory_service: MemoryService,
    memory_id: int,
    new_value: str,
    confidence: float = 0.95,
) -> dict:
    """Update a single memory record's value by its stable row ID.

    Enables intent commands like 'update #42 <new-value>'.
    """
    updated = memory_service.update_by_id(memory_id, new_value, confidence)
    if not updated:
        return {"ok": False, "reason": "memory_not_found", "id": memory_id}
    return {"ok": True, "id": memory_id, "value": new_value}

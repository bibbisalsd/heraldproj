from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from .brain_core.memory_service import MemoryRecord, MemoryService
from .name_profile import first_name
from .pocket_memory import PocketMemoryStore


_DEFAULT_MEMORY_DB_ENV = "JARVIS_MEMORY_DB_PATH"
_SINGLETON_MEMORY_KEYS = (
    "user_name",
    "user_age",
    "user_address_preference",
    "user_name_gender",
    "user_title_preference",
)


class Memory:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = os.getenv(_DEFAULT_MEMORY_DB_ENV, "").strip() or str(
                Path(".jarvis_memory.sqlite").resolve()
            )
        # print(f"DEBUG: Memory using DB at {db_path}")
        self.service = MemoryService(db_path=db_path)
        self.pockets = PocketMemoryStore(db_path=db_path)
        self.service.keep_latest_for_keys(_SINGLETON_MEMORY_KEYS)
        self.pockets.seed_core_pockets()

    def remember(
        self,
        key: str,
        value: str,
        confidence: float,
        *,
        replace_existing: bool = False,
        source: str | None = None,
        source_id: str | None = None,
        utterance: str | None = None,
    ) -> bool:
        """Remember a fact with optional provenance tracking.

        Args:
            key: Memory key
            value: Memory value
            confidence: Confidence score (0.0-1.0)
            source: Source type ("conversation", "tool", "inference")
            source_id: ID of the source (turn_id, tool_call_id, evidence_id)
            utterance: Original utterance that created this memory
        """
        ok = self.service.save(
            key=key,
            value=value,
            confidence=confidence,
            replace_existing=replace_existing,
            source=source,
            source_id=source_id,
            utterance=utterance,
        )
        if ok:
            self._sync_flat_fact_to_pockets(key=key, value=value, confidence=confidence)
        return ok

    def remember_latest(
        self, key: str, value: str, confidence: float, **provenance_kwargs: Any
    ) -> bool:
        return self.remember(
            key=key,
            value=value,
            confidence=confidence,
            replace_existing=True,
            **provenance_kwargs,
        )

    def recall(self, key: str) -> list[MemoryRecord]:
        return self.service.retrieve(key=key)

    def search(
        self,
        query: str,
        top_k: int = 6,
        enable_semantic: bool | None = None,
        embedding_model: str = "nomic-embed-text-v2-moe",
        semantic_threshold: float = 0.58,
        embed_query: Callable[[str], list[float] | None] | None = None,
        embed_document: Callable[[str], list[float] | None] | None = None,
    ) -> list[MemoryRecord]:
        return self.service.search(
            query=query,
            top_k=top_k,
            enable_semantic=enable_semantic,
            embedding_model=embedding_model,
            semantic_threshold=semantic_threshold,
            embed_query=embed_query,
            embed_document=embed_document,
        )

    def purge(self, retention_days: int) -> int:
        return self.service.purge_older_than(days=retention_days)

    def backup(self, backup_dir: str = "./backups") -> str:
        return self.service.backup(backup_dir=backup_dir)

    def restore(self, backup_path: str) -> bool:
        return self.service.restore(backup_path=backup_path)

    def list_backups(self, backup_dir: str = "./backups") -> list[str]:
        return self.service.list_backups(backup_dir=backup_dir)

    def prune_backups(self, backup_dir: str = "./backups", keep: int = 5) -> int:
        return self.service.prune_backups(backup_dir=backup_dir, keep=keep)

    def owner_name(self) -> str | None:
        rows = self.recall("user_name")
        if rows:
            remembered = str(rows[0].value).strip()
            if remembered:
                return remembered
        owner_slot = self.pockets.get_slot("person:owner", "name")
        if owner_slot is not None:
            remembered = owner_slot.slot_value.strip()
            if remembered:
                return remembered
        return None

    def wipe_dynamic_memory(
        self, *, backup_dir: str = "./backups"
    ) -> dict[str, object]:
        backup_path = self.backup(backup_dir=backup_dir)
        flat = self.service.wipe_all_facts()
        pockets = self.pockets.wipe_dynamic_content()
        self.service.keep_latest_for_keys(_SINGLETON_MEMORY_KEYS)
        self.pockets.seed_core_pockets()
        return {
            "backup_path": backup_path,
            "flat": flat,
            "pockets": pockets,
        }

    def _sync_flat_fact_to_pockets(
        self, *, key: str, value: str, confidence: float
    ) -> None:
        normalized_key = str(key).strip().lower()
        normalized_value = str(value).strip()
        if not normalized_key or not normalized_value:
            return

        if normalized_key == "user_name":
            self.pockets.ensure_owner_pocket(canonical_name=normalized_value)
            self.pockets.upsert_entity(
                "person:owner",
                pocket_type="person",
                canonical_name=normalized_value,
                protection_level="dynamic",
                mutable_by="owner",
                allow_update_protected=True,
            )
            self.pockets.set_slot(
                "person:owner",
                "name",
                normalized_value,
                confidence=confidence,
                provenance_type="conversation",
                source="flat_memory_sync",
                protection_level="dynamic",
                allow_update_protected=True,
            )
            given = first_name(normalized_value)
            if given:
                self.pockets.set_slot(
                    "person:owner",
                    "given_name",
                    given,
                    confidence=confidence,
                    provenance_type="conversation",
                    source="flat_memory_sync",
                    protection_level="dynamic",
                    allow_update_protected=True,
                )
            self.pockets.set_link(
                "person:owner",
                "uses_assistant",
                "self:jarvis",
                confidence=confidence,
                provenance_type="conversation",
                source="flat_memory_sync",
                protection_level="dynamic",
                allow_update_protected=True,
            )
            return

        if normalized_key == "user_address_preference":
            self.pockets.ensure_owner_pocket()
            self.pockets.set_slot(
                "person:owner",
                "address_preference",
                normalized_value,
                confidence=confidence,
                provenance_type="conversation",
                source="flat_memory_sync",
                protection_level="dynamic",
                allow_update_protected=True,
            )
            return

        if normalized_key == "user_name_gender":
            self.pockets.ensure_owner_pocket()
            self.pockets.set_slot(
                "person:owner",
                "gender_class",
                normalized_value,
                confidence=confidence,
                provenance_type="conversation",
                source="flat_memory_sync",
                protection_level="dynamic",
                allow_update_protected=True,
            )
            return

        if normalized_key == "user_title_preference":
            self.pockets.ensure_owner_pocket()
            self.pockets.set_slot(
                "person:owner",
                "title_preference",
                normalized_value,
                confidence=confidence,
                provenance_type="conversation",
                source="flat_memory_sync",
                protection_level="dynamic",
                allow_update_protected=True,
            )
            return

        if normalized_key == "user_age":
            self.pockets.ensure_owner_pocket()
            self.pockets.set_slot(
                "person:owner",
                "age",
                normalized_value,
                value_type="integer" if normalized_value.isdigit() else "text",
                confidence=confidence,
                provenance_type="conversation",
                source="flat_memory_sync",
                protection_level="dynamic",
                allow_update_protected=True,
            )
            return

        # Generic sync rule: any key with ":" (P3-5)
        if ":" in normalized_key:
            parts = normalized_key.split(":", 1)
            pocket_name = parts[0]
            slot_name = parts[1]
            if pocket_name and slot_name:
                self.pockets.set_slot(
                    pocket_name,
                    slot_name,
                    normalized_value,
                    confidence=confidence,
                    provenance_type="conversation",
                    source="flat_memory_sync_generic",
                    protection_level="dynamic",
                    allow_update_protected=True,
                )

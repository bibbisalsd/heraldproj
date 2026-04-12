from __future__ import annotations

import sqlite3
import threading
import atexit
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PocketEntity:
    entity_id: str
    pocket_type: str
    canonical_name: str
    protection_level: str
    mutable_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PocketSlot:
    entity_id: str
    slot_key: str
    slot_value: str
    value_type: str
    confidence: float
    provenance_type: str
    source: str
    protection_level: str
    updated_at: str


@dataclass(frozen=True)
class PocketLink:
    source_entity_id: str
    link_type: str
    target_entity_id: str
    confidence: float
    provenance_type: str
    source: str
    protection_level: str
    updated_at: str


class PocketMemoryStore:
    _local = threading.local()

    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        self._init_db()
        atexit.register(self.close_all_connections)

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connections"):
            self._local.connections = {}
        
        if self.db_path not in self._local.connections:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.connections[self.db_path] = conn
        return self._local.connections[self.db_path]

    def close_all_connections(self) -> None:
        """Close thread-local connections if they exist."""
        if hasattr(self._local, "connections"):
            for path, conn in list(self._local.connections.items()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._local.connections.clear()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pocket_entities (
                    entity_id TEXT PRIMARY KEY,
                    pocket_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    protection_level TEXT NOT NULL,
                    mutable_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pocket_slots (
                    entity_id TEXT NOT NULL,
                    slot_key TEXT NOT NULL,
                    slot_value TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    provenance_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    protection_level TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (entity_id, slot_key),
                    FOREIGN KEY (entity_id) REFERENCES pocket_entities(entity_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pocket_links (
                    source_entity_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    provenance_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    protection_level TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source_entity_id, link_type, target_entity_id),
                    FOREIGN KEY (source_entity_id) REFERENCES pocket_entities(entity_id) ON DELETE CASCADE,
                    FOREIGN KEY (target_entity_id) REFERENCES pocket_entities(entity_id) ON DELETE CASCADE
                )
                """
            )

    def upsert_entity(
        self,
        entity_id: str,
        *,
        pocket_type: str,
        canonical_name: str,
        protection_level: str = "dynamic",
        mutable_by: str = "owner",
        allow_update_protected: bool = False,
    ) -> bool:
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT protection_level, canonical_name
                FROM pocket_entities
                WHERE entity_id = ?
                """,
                (entity_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO pocket_entities (
                        entity_id, pocket_type, canonical_name, protection_level, mutable_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        pocket_type,
                        canonical_name,
                        protection_level,
                        mutable_by,
                        now,
                        now,
                    ),
                )
                return True

            existing_protection = str(row[0])
            if existing_protection == "canonical" and not allow_update_protected:
                return False

            conn.execute(
                """
                UPDATE pocket_entities
                SET pocket_type = ?, canonical_name = ?, protection_level = ?, mutable_by = ?, updated_at = ?
                WHERE entity_id = ?
                """,
                (
                    pocket_type,
                    canonical_name,
                    protection_level,
                    mutable_by,
                    now,
                    entity_id,
                ),
            )
            return True

    def set_slot(
        self,
        entity_id: str,
        slot_key: str,
        slot_value: str,
        *,
        value_type: str = "text",
        confidence: float = 0.95,
        provenance_type: str = "conversation",
        source: str = "unknown",
        protection_level: str = "dynamic",
        allow_update_protected: bool = False,
    ) -> bool:
        if confidence < 0.0 or not entity_id.strip() or not slot_key.strip():
            return False

        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT protection_level
                FROM pocket_slots
                WHERE entity_id = ? AND slot_key = ?
                """,
                (entity_id, slot_key),
            ).fetchone()
            if (
                existing is not None
                and str(existing[0]) == "canonical"
                and not allow_update_protected
            ):
                return False

            conn.execute(
                """
                INSERT INTO pocket_slots (
                    entity_id, slot_key, slot_value, value_type, confidence,
                    provenance_type, source, protection_level, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id, slot_key) DO UPDATE SET
                    slot_value = excluded.slot_value,
                    value_type = excluded.value_type,
                    confidence = excluded.confidence,
                    provenance_type = excluded.provenance_type,
                    source = excluded.source,
                    protection_level = excluded.protection_level,
                    updated_at = excluded.updated_at
                """,
                (
                    entity_id,
                    slot_key,
                    slot_value,
                    value_type,
                    confidence,
                    provenance_type,
                    source,
                    protection_level,
                    now,
                ),
            )
            conn.execute(
                "UPDATE pocket_entities SET updated_at = ? WHERE entity_id = ?",
                (now, entity_id),
            )
        return True

    def set_link(
        self,
        source_entity_id: str,
        link_type: str,
        target_entity_id: str,
        *,
        confidence: float = 0.95,
        provenance_type: str = "system",
        source: str = "unknown",
        protection_level: str = "dynamic",
        allow_update_protected: bool = False,
    ) -> bool:
        if (
            not source_entity_id.strip()
            or not target_entity_id.strip()
            or not link_type.strip()
        ):
            return False
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT protection_level
                FROM pocket_links
                WHERE source_entity_id = ? AND link_type = ? AND target_entity_id = ?
                """,
                (source_entity_id, link_type, target_entity_id),
            ).fetchone()
            if (
                existing is not None
                and str(existing[0]) == "canonical"
                and not allow_update_protected
            ):
                return False

            conn.execute(
                """
                INSERT INTO pocket_links (
                    source_entity_id, link_type, target_entity_id, confidence,
                    provenance_type, source, protection_level, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_entity_id, link_type, target_entity_id) DO UPDATE SET
                    confidence = excluded.confidence,
                    provenance_type = excluded.provenance_type,
                    source = excluded.source,
                    protection_level = excluded.protection_level,
                    updated_at = excluded.updated_at
                """,
                (
                    source_entity_id,
                    link_type,
                    target_entity_id,
                    confidence,
                    provenance_type,
                    source,
                    protection_level,
                    now,
                ),
            )
        return True

    def get_entity(self, entity_id: str) -> PocketEntity | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT entity_id, pocket_type, canonical_name, protection_level, mutable_by, created_at, updated_at
                FROM pocket_entities
                WHERE entity_id = ?
                """,
                (entity_id,),
            ).fetchone()
        if row is None:
            return None
        return PocketEntity(*[str(item) for item in row])

    def get_slot(self, entity_id: str, slot_key: str) -> PocketSlot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT entity_id, slot_key, slot_value, value_type, confidence,
                       provenance_type, source, protection_level, updated_at
                FROM pocket_slots
                WHERE entity_id = ? AND slot_key = ?
                """,
                (entity_id, slot_key),
            ).fetchone()
        if row is None:
            return None
        return PocketSlot(
            entity_id=str(row[0]),
            slot_key=str(row[1]),
            slot_value=str(row[2]),
            value_type=str(row[3]),
            confidence=float(row[4]),
            provenance_type=str(row[5]),
            source=str(row[6]),
            protection_level=str(row[7]),
            updated_at=str(row[8]),
        )

    def list_slots(self, entity_id: str) -> list[PocketSlot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT entity_id, slot_key, slot_value, value_type, confidence,
                       provenance_type, source, protection_level, updated_at
                FROM pocket_slots
                WHERE entity_id = ?
                ORDER BY slot_key
                """,
                (entity_id,),
            ).fetchall()
        return [
            PocketSlot(
                entity_id=str(row[0]),
                slot_key=str(row[1]),
                slot_value=str(row[2]),
                value_type=str(row[3]),
                confidence=float(row[4]),
                provenance_type=str(row[5]),
                source=str(row[6]),
                protection_level=str(row[7]),
                updated_at=str(row[8]),
            )
            for row in rows
        ]

    def slot_map(self, entity_id: str) -> dict[str, PocketSlot]:
        return {slot.slot_key: slot for slot in self.list_slots(entity_id)}

    def related_entities(self, entity_id: str) -> list[PocketLink]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_entity_id, link_type, target_entity_id, confidence,
                       provenance_type, source, protection_level, updated_at
                FROM pocket_links
                WHERE source_entity_id = ?
                ORDER BY confidence DESC, target_entity_id ASC
                """,
                (entity_id,),
            ).fetchall()
        return [
            PocketLink(
                source_entity_id=str(row[0]),
                link_type=str(row[1]),
                target_entity_id=str(row[2]),
                confidence=float(row[3]),
                provenance_type=str(row[4]),
                source=str(row[5]),
                protection_level=str(row[6]),
                updated_at=str(row[7]),
            )
            for row in rows
        ]

    def related_entity_ids(self, entity_id: str) -> list[str]:
        return [link.target_entity_id for link in self.related_entities(entity_id)]

    def resolve_reference(
        self, reference: str, *, speaker_entity_id: str = "person:owner"
    ) -> str | None:
        normalized = "".join(
            ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in str(reference)
        ).strip()
        normalized = " ".join(normalized.split())
        if not normalized:
            return None

        if normalized in {"i", "me", "my", "myself"}:
            return speaker_entity_id
        if normalized in {"you", "yourself", "jarvis"}:
            return "self:jarvis"
        if normalized in {
            "jarvis codebase",
            "the codebase",
            "your codebase",
            "jarviscore",
            "repo",
            "repository",
        }:
            return "codebase:jarviscore"
        if normalized in {"jarvis project", "the project", "your project"}:
            return "project:jarvis"
        if normalized in {"your personality", "persona", "personality"}:
            return "persona:jarvis"
        return None

    def relevant_entity_ids(
        self, entity_id: str, *, include_self: bool = True, limit: int = 8
    ) -> list[str]:
        ordered: list[str] = []
        if include_self:
            ordered.append(entity_id)
        for link in self.related_entities(entity_id):
            if link.target_entity_id not in ordered:
                ordered.append(link.target_entity_id)
            if len(ordered) >= limit:
                break
        return ordered[:limit]

    def ensure_owner_pocket(self, *, canonical_name: str = "Owner") -> None:
        self.upsert_entity(
            "person:owner",
            pocket_type="person",
            canonical_name=canonical_name,
            protection_level="dynamic",
            mutable_by="owner",
            allow_update_protected=True,
        )

    def wipe_dynamic_content(
        self, *, preserve_entity_ids: Iterable[str] | None = None
    ) -> dict[str, int]:
        preserved = {
            str(entity_id).strip()
            for entity_id in (preserve_entity_ids or [])
            if str(entity_id).strip()
        }
        with self._connect() as conn:
            deleted_links = 0
            deleted_slots = 0
            deleted_entities = 0

            if preserved:
                placeholders = ", ".join("?" for _ in preserved)
                cur = conn.execute(
                    f"""
                    DELETE FROM pocket_links
                    WHERE protection_level <> 'canonical'
                      AND source_entity_id NOT IN ({placeholders})
                      AND target_entity_id NOT IN ({placeholders})
                    """,
                    tuple(preserved) + tuple(preserved),
                )
                deleted_links += int(cur.rowcount)
                cur = conn.execute(
                    f"""
                    DELETE FROM pocket_slots
                    WHERE protection_level <> 'canonical'
                      AND entity_id NOT IN ({placeholders})
                    """,
                    tuple(preserved),
                )
                deleted_slots += int(cur.rowcount)
                cur = conn.execute(
                    f"""
                    DELETE FROM pocket_entities
                    WHERE protection_level <> 'canonical'
                      AND entity_id NOT IN ({placeholders})
                    """,
                    tuple(preserved),
                )
                deleted_entities += int(cur.rowcount)
            else:
                cur = conn.execute(
                    "DELETE FROM pocket_links WHERE protection_level <> 'canonical'"
                )
                deleted_links += int(cur.rowcount)
                cur = conn.execute(
                    "DELETE FROM pocket_slots WHERE protection_level <> 'canonical'"
                )
                deleted_slots += int(cur.rowcount)
                cur = conn.execute(
                    "DELETE FROM pocket_entities WHERE protection_level <> 'canonical'"
                )
                deleted_entities += int(cur.rowcount)

        self.seed_core_pockets()
        return {
            "deleted_links": deleted_links,
            "deleted_slots": deleted_slots,
            "deleted_entities": deleted_entities,
        }

    def seed_core_pockets(self) -> None:
        from .config import build_default_config, JARVIS_VERSION

        cfg = build_default_config()
        repo_root = Path(__file__).resolve().parents[1]
        package_root = repo_root / "jarvis"

        canonical_entities = [
            ("self:jarvis", "self", "Jarvis"),
            ("persona:jarvis", "persona", "Jarvis Persona"),
            ("project:jarvis", "project", "Jarvis"),
            ("codebase:jarviscore", "codebase", "Jarviscore"),
            ("person:creator_james", "person", "James"),
            ("person:creator_bxserkk", "person", "bxserkk"),
            ("architecture:herald_skeptic", "architecture", "Herald → Skeptic"),
            ("tool:calculator", "tool", "Calculator"),
            ("tool:local_now", "tool", "Local Time"),
            ("tool:utc_now_iso", "tool", "UTC Time"),
            ("tool:file_write", "tool", "File Write"),
            ("tool:code_runner", "tool", "Code Runner"),
            ("tool:app_launch", "tool", "App Launch"),
            ("tool:app_focus", "tool", "App Focus"),
            ("tool:memory", "tool", "Memory"),
            ("tool:vision", "tool", "Vision"),
            ("tool:code_inspection", "tool", "Code Inspection"),
            ("tool:job_status", "tool", "Job Status"),
            ("module:main_runtime", "module", "Main Runtime"),
            ("module:voice_runtime", "module", "Voice Runtime"),
            ("module:prompt_dispatcher", "module", "Prompt Dispatcher"),
            ("module:intent_handlers", "module", "Intent Handlers"),
            ("module:memory", "module", "Memory"),
            ("module:bg1_queue", "module", "BG1 Queue"),
        ]

        for entity_id, pocket_type, canonical_name in canonical_entities:
            self.upsert_entity(
                entity_id,
                pocket_type=pocket_type,
                canonical_name=canonical_name,
                protection_level="canonical",
                mutable_by="system",
                allow_update_protected=True,
            )

        canonical_slots = [
            ("self:jarvis", "name", "Jarvis"),
            ("self:jarvis", "version", JARVIS_VERSION),
            ("self:jarvis", "assistant_type", "local_ai_assistant"),
            ("self:jarvis", "wake_word", cfg.wake_word_phrase),
            ("self:jarvis", "runtime_location", "this computer"),
            (
                "self:jarvis",
                "identity_summary",
                "I am Jarvis, a local AI assistant running on this computer.",
            ),
            (
                "self:jarvis",
                "capabilities_summary",
                "I can answer quick questions, run heavy BG1 tasks, report job status, remember stable facts, inspect local code, inspect the local screen, do arithmetic, and tell the time.",
            ),
            (
                "self:jarvis",
                "runtime_flow_summary",
                "I listen through the voice runtime, route text with the prompt dispatcher, answer deterministic intents first, use tools and specialists when needed, and use the local model only when a request is still unresolved.",
            ),
            (
                "self:jarvis",
                "creator_summary",
                "I was created by James, who goes by gxzx, and bxserkk, who is referred to as berserk.",
            ),
            (
                "self:jarvis",
                "architecture_summary",
                "I was created using the Herald to Skeptic architecture.",
            ),
            ("persona:jarvis", "tone", "concise_direct_calm"),
            ("persona:jarvis", "truthfulness_rule", "do_not_guess"),
            ("persona:jarvis", "style_rule", "ask_or_refuse_when_unverified"),
            ("project:jarvis", "project_name", "Jarvis"),
            ("project:jarvis", "purpose", "local_integrated_ai_assistant"),
            (
                "project:jarvis",
                "spoken_purpose",
                "quick local assistance with deterministic routing and optional heavy background work",
            ),
            ("project:jarvis", "repo_name", "Jarviscore"),
            (
                "project:jarvis",
                "creator_summary",
                "James, who goes by gxzx, and bxserkk, who is referred to as berserk, created this project.",
            ),
            ("codebase:jarviscore", "repo_root", str(repo_root)),
            ("codebase:jarviscore", "package_root", str(package_root)),
            (
                "codebase:jarviscore",
                "entry_voice",
                str(repo_root / "scripts" / "run_voice.ps1"),
            ),
            (
                "codebase:jarviscore",
                "entry_chat",
                str(repo_root / "scripts" / "run_chat.ps1"),
            ),
            (
                "codebase:jarviscore",
                "entry_launcher",
                str(repo_root / "start_jarvis.bat"),
            ),
            ("person:creator_james", "name", "James"),
            ("person:creator_james", "handle", "gxzx"),
            ("person:creator_james", "spoken_handle", "gxzx"),
            ("person:creator_james", "country", "United Kingdom"),
            ("person:creator_james", "role", "creator"),
            ("person:creator_bxserkk", "handle", "bxserkk"),
            ("person:creator_bxserkk", "spoken_name", "berserk"),
            ("person:creator_bxserkk", "country", "United States"),
            ("person:creator_bxserkk", "role", "creator"),
            ("person:creator_bxserkk", "real_name_known", "false"),
            ("architecture:herald_skeptic", "name", "Herald → Skeptic"),
            (
                "architecture:herald_skeptic",
                "spoken_name",
                "Herald to Skeptic architecture",
            ),
            (
                "architecture:herald_skeptic",
                "description",
                "Jarvis was created using the Herald to Skeptic architecture.",
            ),
            ("tool:calculator", "tool_name", "calculator"),
            ("tool:calculator", "purpose", "deterministic_arithmetic"),
            ("tool:calculator", "spoken_purpose", "deterministic arithmetic"),
            ("tool:local_now", "tool_name", "local_now"),
            ("tool:local_now", "purpose", "local_time_lookup"),
            ("tool:local_now", "spoken_purpose", "local time lookup"),
            ("tool:utc_now_iso", "tool_name", "utc_now_iso"),
            ("tool:utc_now_iso", "purpose", "utc_time_lookup"),
            ("tool:utc_now_iso", "spoken_purpose", "UTC time lookup"),
            ("tool:file_write", "tool_name", "file_write"),
            ("tool:file_write", "purpose", "workspace_file_write"),
            ("tool:file_write", "spoken_purpose", "writing files inside the workspace"),
            ("tool:code_runner", "tool_name", "code_runner"),
            ("tool:code_runner", "purpose", "python_execution"),
            ("tool:code_runner", "spoken_purpose", "running local Python code"),
            ("tool:app_launch", "tool_name", "app_launch"),
            ("tool:app_launch", "purpose", "launch_local_application"),
            ("tool:app_launch", "spoken_purpose", "launching local applications"),
            ("tool:app_focus", "tool_name", "app_focus"),
            ("tool:app_focus", "purpose", "focus_local_application"),
            (
                "tool:app_focus",
                "spoken_purpose",
                "bringing local applications into focus",
            ),
            ("tool:memory", "tool_name", "memory"),
            ("tool:memory", "purpose", "remember_and_recall_stable_facts"),
            ("tool:memory", "spoken_purpose", "remembering and recalling stable facts"),
            ("tool:vision", "tool_name", "vision"),
            ("tool:vision", "purpose", "inspect_local_screen_or_images"),
            ("tool:vision", "spoken_purpose", "inspecting the local screen or images"),
            ("tool:code_inspection", "tool_name", "code_inspection"),
            ("tool:code_inspection", "purpose", "inspect_local_codebase"),
            ("tool:code_inspection", "spoken_purpose", "inspecting the local codebase"),
            ("tool:job_status", "tool_name", "job_status"),
            ("tool:job_status", "purpose", "report_and_manage_bg1_status"),
            ("tool:job_status", "spoken_purpose", "reporting and managing BG1 status"),
            ("module:main_runtime", "file_path", str(package_root / "main.py")),
            (
                "module:main_runtime",
                "purpose",
                "main_turn_processing_runtime_and_output",
            ),
            (
                "module:main_runtime",
                "spoken_purpose",
                "main turn processing and output delivery",
            ),
            (
                "module:voice_runtime",
                "file_path",
                str(package_root / "voice" / "runtime.py"),
            ),
            (
                "module:voice_runtime",
                "purpose",
                "mic_capture_stt_passive_voice_runtime",
            ),
            (
                "module:voice_runtime",
                "spoken_purpose",
                "microphone capture, STT, and passive voice turns",
            ),
            (
                "module:prompt_dispatcher",
                "file_path",
                str(package_root / "brain_core" / "prompt_dispatcher.py"),
            ),
            (
                "module:prompt_dispatcher",
                "purpose",
                "normalize_route_exact_semantic_classifier",
            ),
            (
                "module:prompt_dispatcher",
                "spoken_purpose",
                "normalizing input and routing requests",
            ),
            (
                "module:intent_handlers",
                "file_path",
                str(package_root / "brain_core" / "intent_handlers.py"),
            ),
            (
                "module:intent_handlers",
                "purpose",
                "brain_first_deterministic_intent_handling",
            ),
            (
                "module:intent_handlers",
                "spoken_purpose",
                "brain first deterministic intent handling",
            ),
            ("module:memory", "file_path", str(package_root / "memory.py")),
            ("module:memory", "purpose", "flat_memory_and_pocket_bridge"),
            (
                "module:memory",
                "spoken_purpose",
                "bridging flat memory and pocket memory",
            ),
            (
                "module:bg1_queue",
                "file_path",
                str(package_root / "brain_core" / "bg1_queue.py"),
            ),
            ("module:bg1_queue", "purpose", "queue_and_track_heavy_bg1_tasks"),
            (
                "module:bg1_queue",
                "spoken_purpose",
                "queuing and tracking heavy BG1 tasks",
            ),
        ]
        for entity_id, slot_key, slot_value in canonical_slots:
            self.set_slot(
                entity_id,
                slot_key,
                slot_value,
                provenance_type="system_seed",
                source="seed_core_pockets",
                protection_level="canonical",
                allow_update_protected=True,
            )

        canonical_links = [
            ("self:jarvis", "has_persona", "persona:jarvis"),
            ("self:jarvis", "belongs_to_project", "project:jarvis"),
            ("self:jarvis", "implemented_in", "codebase:jarviscore"),
            ("self:jarvis", "created_by", "person:creator_james"),
            ("self:jarvis", "created_by", "person:creator_bxserkk"),
            ("self:jarvis", "uses_architecture", "architecture:herald_skeptic"),
            ("project:jarvis", "implemented_in", "codebase:jarviscore"),
            ("project:jarvis", "created_by", "person:creator_james"),
            ("project:jarvis", "created_by", "person:creator_bxserkk"),
            ("project:jarvis", "uses_architecture", "architecture:herald_skeptic"),
            ("architecture:herald_skeptic", "authored_by", "person:creator_james"),
            ("architecture:herald_skeptic", "authored_by", "person:creator_bxserkk"),
            ("self:jarvis", "has_tool", "tool:calculator"),
            ("self:jarvis", "has_tool", "tool:local_now"),
            ("self:jarvis", "has_tool", "tool:utc_now_iso"),
            ("self:jarvis", "has_tool", "tool:file_write"),
            ("self:jarvis", "has_tool", "tool:code_runner"),
            ("self:jarvis", "has_tool", "tool:app_launch"),
            ("self:jarvis", "has_tool", "tool:app_focus"),
            ("self:jarvis", "has_tool", "tool:memory"),
            ("self:jarvis", "has_tool", "tool:vision"),
            ("self:jarvis", "has_tool", "tool:code_inspection"),
            ("self:jarvis", "has_tool", "tool:job_status"),
            ("codebase:jarviscore", "contains_module", "module:main_runtime"),
            ("codebase:jarviscore", "contains_module", "module:voice_runtime"),
            ("codebase:jarviscore", "contains_module", "module:prompt_dispatcher"),
            ("codebase:jarviscore", "contains_module", "module:intent_handlers"),
            ("codebase:jarviscore", "contains_module", "module:memory"),
            ("codebase:jarviscore", "contains_module", "module:bg1_queue"),
        ]
        for source_entity_id, link_type, target_entity_id in canonical_links:
            self.set_link(
                source_entity_id,
                link_type,
                target_entity_id,
                provenance_type="system_seed",
                source="seed_core_pockets",
                protection_level="canonical",
                allow_update_protected=True,
            )

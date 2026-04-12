from __future__ import annotations

import json
import os
import sqlite3
import threading
import atexit
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple
from jarvis.observability.events import PersistentEventLogger


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# NH-CRSIS Task H: Contradiction Guard - Negation pairs
CONTRADICTION_NEGATION_PAIRS = [
    ("yes", "no"),
    ("true", "false"),
    ("on", "off"),
    ("enabled", "disabled"),
    ("active", "inactive"),
    ("running", "stopped"),
    ("open", "closed"),
    ("allowed", "denied"),
    ("connected", "disconnected"),
]

# NH-CRSIS Task I: Confidence Decay - Half-life in days
DECAY_HALF_LIFE_DAYS: int = 30  # Confidence halves every 30 days


@dataclass
class MemoryRecord:
    key: str
    value: str
    confidence: float
    created_at: str
    id: int | None = None
    match_type: str = "exact"
    score: float = 1.0
    # Provenance tracking (Task G + P)
    source: str | None = None  # "conversation", "tool", "inference"
    source_id: str | None = None  # turn_id, tool_call_id, or evidence_id
    utterance: str | None = None  # Original utterance that created this memory


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_memory_enabled() -> bool:
    raw = os.getenv("JARVIS_ENABLE_SEMANTIC_MEMORY_RETRIEVAL", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class MemoryService:
    """Memory service with NH-CRSIS Task H: Contradiction Guard.

    Before inserting a fact, checks whether it contradicts an existing fact
    for the same key. If so, emits a memory_contradiction event and blocks
    the insert unless force_save() is used.
    """

    _local = threading.local()

    def __init__(self, db_path: str, log_dir: str = "./logs") -> None:
        db_p = Path(db_path)
        if not db_p.parent.exists():
            db_p.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_p)
        self._log_dir = log_dir
        self._event_logger = PersistentEventLogger(log_dir)
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
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    namespace TEXT DEFAULT 'user',
                    source TEXT,
                    source_id TEXT,
                    utterance TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (memory_id, model),
                    FOREIGN KEY (memory_id) REFERENCES memory_facts(id) ON DELETE CASCADE
                )
                """
            )
            # Add provenance and namespace columns to existing tables (migration)
            for col, col_type in [
                ("source", "TEXT"),
                ("source_id", "TEXT"),
                ("utterance", "TEXT"),
                ("namespace", "TEXT DEFAULT 'user'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE memory_facts ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass  # Column already exists

    def save(
        self,
        key: str,
        value: str,
        confidence: float,
        *,
        namespace: str = "user",
        replace_existing: bool = False,
        source: str | None = None,
        source_id: str | None = None,
        utterance: str | None = None,
    ) -> bool:
        """Save a memory fact with optional provenance tracking and namespace.

        NH-CRSIS Task H: Contradiction Guard
        Before inserting, checks whether the new value contradicts an existing
        fact for the same key. If so, emits a memory_contradiction event and
        blocks the insert.

        Note: If replace_existing=True, the contradiction check is bypassed to
        allow intentional updates to singleton keys (e.g., user_name).

        Args:
            key: Memory key
            value: Memory value
            confidence: Confidence score (0.0-1.0)
            namespace: Memory namespace (default: "user")
            source: Source type ("conversation", "tool", "inference")
            source_id: ID of the source (turn_id, tool_call_id, evidence_id)
            utterance: Original utterance that created this memory

        Returns:
            True if saved successfully, False if blocked by contradiction or low confidence
        """
        if confidence < 0.75:
            return False

        # NH-CRSIS Task H: Contradiction check
        if not replace_existing:
            existing = self._retrieve_all(key, namespace=namespace)
            for record in existing:
                if self._is_contradiction(record.value, value):
                    self._emit_contradiction_event(key, record.value, value)
                    return False

        with self._connect() as conn:
            if replace_existing:
                conn.execute("DELETE FROM memory_facts WHERE key = ? AND namespace = ?", (key, namespace))
            conn.execute(
                """
                INSERT INTO memory_facts (key, value, confidence, created_at, namespace, source, source_id, utterance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    value,
                    confidence,
                    _utc_now().isoformat(),
                    namespace,
                    source,
                    source_id,
                    utterance,
                ),
            )
        return True

    def force_save(
        self,
        key: str,
        value: str,
        confidence: float = 1.0,
        *,
        namespace: str = "user",
        replace_existing: bool = False,
        source: str | None = None,
        source_id: str | None = None,
        utterance: str | None = None,
    ) -> bool:
        """Save a memory fact bypassing contradiction check."""
        if confidence < 0.75:
            return False
        with self._connect() as conn:
            if replace_existing:
                conn.execute("DELETE FROM memory_facts WHERE key = ? AND namespace = ?", (key, namespace))
            conn.execute(
                """
                INSERT INTO memory_facts (key, value, confidence, created_at, namespace, source, source_id, utterance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    value,
                    confidence,
                    _utc_now().isoformat(),
                    namespace,
                    source,
                    source_id,
                    utterance,
                ),
            )
        return True

    # ========================================================================
    # NH-CRSIS Task H: Contradiction Guard Methods
    # ========================================================================

    def _is_contradiction(self, existing_value: str, new_value: str) -> bool:
        """Lightweight lexical contradiction check.

        NH-CRSIS Task H: Contradiction Guard
        Detects direct negation patterns without an embedding model.
        Returns True if the values appear to contradict each other.
        """
        ev = existing_value.lower().strip()
        nv = new_value.lower().strip()

        # Check for direct negation pairs
        for a, b in CONTRADICTION_NEGATION_PAIRS:
            if (a in ev and b in nv) or (b in ev and a in nv):
                return True

        # Exact same value is not a contradiction
        if ev == nv:
            return False

        # Only negation pairs (yes/no, on/off, etc.) are true contradictions.
        # Different values for the same key (e.g. two different names) are
        # updates, not contradictions — do NOT block them here.
        return False

    def _emit_contradiction_event(
        self, key: str, existing_value: str, new_value: str
    ) -> None:
        """Emit memory_contradiction event to log.

        NH-CRSIS Task H: Contradiction Guard - Observability
        """
        from jarvis.observability.events import EventRecord

        self._event_logger.emit(
            EventRecord.build(
                event_type="memory_contradiction",
                turn_id="unknown",
                lane_decision="memory_save",
                resolved_by="contradiction_guard",
                elapsed_ms=0,
                addon_id=json.dumps(
                    {
                        "key": key,
                        "existing_value": existing_value,
                        "new_value": new_value,
                    }
                ),
            )
        )

    # ========================================================================
    # End NH-CRSIS Task H Methods
    # ========================================================================

    # ========================================================================
    # NH-CRSIS Task I: Confidence Decay Methods
    # ========================================================================

    def _decayed_confidence(self, confidence: float, created_at: str) -> float:
        """Apply exponential decay based on age.

        NH-CRSIS Task I: Confidence Decay
        Facts lose confidence over time with a configurable half-life.
        Default: 30-day half-life (confidence halves every 30 days).

        Args:
            confidence: Original confidence score (0.0-1.0)
            created_at: ISO timestamp when fact was created

        Returns:
            Decayed confidence score
        """
        try:
            created = datetime.fromisoformat(created_at)
            age_days = (datetime.now(timezone.utc) - created).days
            decay = 0.5 ** (age_days / DECAY_HALF_LIFE_DAYS)
            return confidence * decay
        except (ValueError, TypeError):
            # Graceful fallback on bad timestamp
            return confidence

    def retrieve(self, key: str, namespace: str | None = None) -> list[MemoryRecord]:
        """Retrieve memory records filtered by decayed confidence and optional namespace.

        NH-CRSIS Task I: Confidence Decay
        Only returns records whose decayed confidence meets the threshold (0.75).

        Args:
            key: Memory key to retrieve
            namespace: Optional namespace filter

        Returns: list of MemoryRecord objects with decayed confidence >= threshold
        """
        query = """
            SELECT id, key, value, confidence, created_at, source, source_id, utterance, namespace
            FROM memory_facts WHERE key = ?
        """
        params = [key]
        if namespace:
            query += " AND namespace = ?"
            params.append(namespace)
        query += " ORDER BY id DESC"

        with self._connect() as conn:
            rows: list[Tuple] = conn.execute(query, params).fetchall()

        result = []
        for (
            memory_id,
            key_value,
            value,
            confidence,
            created_at,
            source,
            source_id,
            utterance,
            ns,
        ) in rows:
            # Filter by decayed confidence
            if self._decayed_confidence(confidence, created_at) >= 0.75:
                result.append(
                    MemoryRecord(
                        key=key_value,
                        value=value,
                        confidence=confidence,
                        created_at=created_at,
                        id=memory_id,
                        source=source,
                        source_id=source_id,
                        utterance=utterance,
                    )
                )
        return result

    def retrieve_with_decay_scores(
        self, key: str, namespace: str | None = None
    ) -> list[tuple[MemoryRecord, float]]:
        """Retrieve memory records with their decayed confidence scores."""
        records = self.retrieve(key, namespace=namespace)
        return [
            (r, self._decayed_confidence(r.confidence, r.created_at)) for r in records
        ]

    def _retrieve_all(self, key: str, namespace: str | None = None) -> list[MemoryRecord]:
        """Retrieve ALL memory records for a key without decay filtering."""
        query = """
            SELECT id, key, value, confidence, created_at, source, source_id, utterance, namespace
            FROM memory_facts WHERE key = ?
        """
        params = [key]
        if namespace:
            query += " AND namespace = ?"
            params.append(namespace)
        query += " ORDER BY id DESC"

        with self._connect() as conn:
            rows: list[Tuple] = conn.execute(query, params).fetchall()
        return [
            MemoryRecord(
                key=key_value,
                value=value,
                confidence=confidence,
                created_at=created_at,
                id=memory_id,
                source=source,
                source_id=source_id,
                utterance=utterance,
            )
            for memory_id, key_value, value, confidence, created_at, source, source_id, utterance, ns in rows
        ]

    def search(
        self,
        query: str,
        top_k: int = 6,
        enable_semantic: bool | None = None,
        embedding_model: str = "nomic-embed-text-v2-moe",
        semantic_threshold: float = 0.58,
        embed_query: Callable[[str], list[float] | None] | None = None,
        embed_document: Callable[[str], list[float] | None] | None = None,
        keep_alive: str = "2h",
        namespace: str | None = None,
    ) -> list[MemoryRecord]:
        if top_k <= 0:
            return []

        results: list[MemoryRecord] = []
        seen_ids: set[int] = set()

        for row in self.retrieve(query, namespace=namespace):
            if row.id is not None:
                seen_ids.add(row.id)
            results.append(row)
            if len(results) >= top_k:
                return results[:top_k]

        if enable_semantic is None:
            enable_semantic = _semantic_memory_enabled()
        if not enable_semantic:
            return results[:top_k]

        # Fast-path: skip semantic search for ephemeral queries that won't benefit
        if self._is_ephemeral_query(query):
            return results[:top_k]

        if embed_query is None or embed_document is None:
            embed_query, embed_document = self._build_default_embedders(
                model=embedding_model, keep_alive=keep_alive
            )

        query_vector = embed_query(query)
        if not query_vector:
            return results[:top_k]

        semantic_matches = self._semantic_matches(
            query_vector=query_vector,
            embedding_model=embedding_model,
            semantic_threshold=semantic_threshold,
            embed_document=embed_document,
            namespace=namespace,
        )
        for row in semantic_matches:
            if row.id is not None and row.id in seen_ids:
                continue
            if row.id is not None:
                seen_ids.add(row.id)
            results.append(row)
            if len(results) >= top_k:
                break
        return results[:top_k]

    def _is_ephemeral_query(self, query: str) -> bool:
        """Check if query is ephemeral and unlikely to benefit from semantic search.

        Ephemeral queries (time, date, greetings, simple acknowledgments) don't
        need semantic memory retrieval - they're resolved by tools or generic
        responses. Skip the expensive embedding generation for these.
        """
        q = query.lower().strip()

        # Remove common wake words to check the actual intent
        for wake in ("jarvis", "hey jarvis", "ok jarvis", "hey", "ok", "alexa", "siri"):
            if q.startswith(wake + ",") or q.startswith(wake + " "):
                q = q[len(wake) :].strip().lstrip(",").strip()
                break

        # Time/date queries
        if q.startswith(
            (
                "what time",
                "what's the time",
                "what is the time",
                "current time",
                "tell me the time",
            )
        ):
            return True
        if q.startswith(
            (
                "what day",
                "what's the date",
                "what is the date",
                "current date",
                "today is",
            )
        ):
            return True
        # Also catch "what's the day" pattern
        if q.startswith("what's the day") or q.startswith("what is the day"):
            return True

        # Greetings and farewells
        if q in (
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "goodbye",
            "bye",
        ):
            return True
        if q.startswith(
            ("hello", "hi ", "hey ", "good morning", "good afternoon", "good evening")
        ):
            return True

        # Wellbeing/status queries (handled by template, not memory)
        if q.startswith(
            (
                "how are you",
                "how're you",
                "how r u",
                "how is it going",
                "how's it going",
            )
        ):
            return True
        if "how are you" in q or "how're you" in q or "how is it going" in q:
            return True

        # Performance/speed/latency queries (handled by template or realtime logic, not memory)
        if any(
            word in q
            for x in ("faster", "slower", "slow", "lag", "latency", "latency")
            for word in (x,)
        ):
            return True
        if "speed" in q and "internet" not in q:
            return True
        if q.startswith(
            ("are you faster", "are you slower", "why are you", "why are responses")
        ):
            return True

        # Simple acknowledgments / filler
        if q in ("thanks", "thank you", "ok", "okay", "sure", "yes", "no", "maybe"):
            return True
        if q.startswith(("thanks", "thank you")):
            return True

        # Weather queries (handled by tool, not memory)
        if "weather" in q:
            return True

        # Purpose/identity queries (handled by template)
        if q.startswith(
            ("what is your purpose", "what's your purpose", "what are you")
        ):
            return True

        # Navigation commands (handled by tool)
        if q.startswith(("go to ", "navigate to ", "open ", "visit ")):
            return True

        # Codebase task queries (handled by code specialist, not memory).
        # Only skip semantic search when the query is clearly a codebase task,
        # not when it's incidentally about code (e.g. "memories about code").
        codebase_task_words = {
            "audit",
            "refactor",
            "debug",
            "inspect",
            "look into",
            "work on",
            "work with",
            "start working",
            "improve",
        }
        if ("codebase" in q or "repo" in q or "repository" in q) and any(
            x in q for x in codebase_task_words
        ):
            return True
        if (
            "code" in q
            and not any(x in q for x in ("memories", "memory", "remember"))
            and any(x in q for x in codebase_task_words)
        ):
            return True

        return False

    def forget_by_id(self, memory_id: int) -> bool:
        """Delete a single memory record by its stable row ID.

        Phase 3C: Memory Productization — granular forget.
        Enables intent commands like 'forget #42'.

        Args:
            memory_id: Integer row ID of the memory to delete.

        Returns:
            True if a record was deleted, False if no such ID exists.
        """
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_facts WHERE id = ?", (memory_id,))
            # Also clean up any associated embeddings
            conn.execute(
                "DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,)
            )
        return int(cur.rowcount) > 0

    def update_by_id(
        self,
        memory_id: int,
        new_value: str,
        confidence: float = 0.95,
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> bool:
        """Update a single memory record's value by its stable row ID.

        Phase 3C: Memory Productization — granular edit.
        Enables intent commands like 'update #42 <new-value>'.
        Uses force-update semantics (bypasses contradiction guard).

        Args:
            memory_id: Integer row ID of the memory to update.
            new_value: New value string.
            confidence: New confidence score (default 0.95).
            source: Optional provenance source.
            source_id: Optional provenance source ID.

        Returns:
            True if a record was updated, False if no such ID exists.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE memory_facts
                SET value = ?, confidence = ?, source = ?, source_id = ?
                WHERE id = ?
                """,
                (new_value, confidence, source, source_id, memory_id),
            )
            if int(cur.rowcount) > 0:
                # Invalidate cached embedding so it gets recomputed on next search
                conn.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,)
                )
                return True
        return False

    def get_by_id(self, memory_id: int) -> Optional["MemoryRecord"]:
        """Retrieve a single memory record by its stable row ID.

        Args:
            memory_id: Integer row ID.

        Returns:
            MemoryRecord if found, None otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, key, value, confidence, created_at, source, source_id, utterance
                FROM memory_facts WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
        if row is None:
            return None
        (
            memory_id_val,
            key,
            value,
            confidence,
            created_at,
            source,
            source_id,
            utterance,
        ) = row
        return MemoryRecord(
            key=key,
            value=value,
            confidence=confidence,
            created_at=created_at,
            id=memory_id_val,
            source=source,
            source_id=source_id,
            utterance=utterance,
        )

    def purge_older_than(self, days: int) -> int:
        cutoff = (_utc_now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM memory_facts WHERE created_at < ?", (cutoff,)
            )
        return int(cur.rowcount)

    def wipe_all_facts(self) -> dict[str, int]:
        with self._connect() as conn:
            embeddings = conn.execute("DELETE FROM memory_embeddings")
            facts = conn.execute("DELETE FROM memory_facts")
        return {
            "deleted_embeddings": int(embeddings.rowcount),
            "deleted_facts": int(facts.rowcount),
        }

    def keep_latest_for_keys(self, keys: Iterable[str]) -> int:
        removed = 0
        normalized = [str(key).strip() for key in keys if str(key).strip()]
        if not normalized:
            return removed

        with self._connect() as conn:
            for key in normalized:
                current = conn.execute(
                    "SELECT MAX(id) FROM memory_facts WHERE key = ?",
                    (key,),
                ).fetchone()
                keep_id = current[0] if current else None
                if keep_id is None:
                    continue
                cur = conn.execute(
                    "DELETE FROM memory_facts WHERE key = ? AND id <> ?",
                    (key, keep_id),
                )
                removed += int(cur.rowcount)
        return removed

    def backup(self, backup_dir: str = "./backups") -> str:
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        timestamp = _utc_now().strftime("%Y%m%d_%H%M%S")
        dest = backup_path / f"memory_backup_{timestamp}.sqlite"
        if dest.exists():
            index = 1
            while True:
                candidate = backup_path / f"memory_backup_{timestamp}_{index}.sqlite"
                if not candidate.exists():
                    dest = candidate
                    break
                index += 1
        escaped = str(dest).replace("'", "''")
        with self._connect() as conn:
            conn.execute(f"VACUUM INTO '{escaped}'")
        return str(dest)

    def restore(self, backup_path: str) -> bool:
        backup = Path(backup_path)
        if not backup.exists():
            return False
        with sqlite3.connect(str(backup)) as source:
            with sqlite3.connect(self.db_path) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=WAL;")
        return True

    def list_backups(self, backup_dir: str = "./backups") -> list[str]:
        backup_path = Path(backup_dir)
        if not backup_path.exists():
            return []
        backups = sorted(
            backup_path.glob("memory_backup_*.sqlite"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return [str(path) for path in backups]

    def prune_backups(self, backup_dir: str = "./backups", keep: int = 5) -> int:
        backups = self.list_backups(backup_dir)
        to_remove = backups[max(0, keep) :]
        for path in to_remove:
            Path(path).unlink(missing_ok=True)
        return len(to_remove)

    def _semantic_matches(
        self,
        query_vector: list[float],
        embedding_model: str,
        semantic_threshold: float,
        embed_document: Callable[[str], list[float] | None],
        namespace: str | None = None,
    ) -> list[MemoryRecord]:
        pending_vectors: list[tuple[int, str]] = []
        rows: list[MemoryRecord] = []

        query = """
            SELECT f.id, f.key, f.value, f.confidence, f.created_at, e.vector_json, f.source, f.source_id, f.utterance, f.namespace
            FROM memory_facts AS f
            LEFT JOIN memory_embeddings AS e
              ON e.memory_id = f.id AND e.model = ?
        """
        params = [embedding_model]
        if namespace:
            query += " WHERE f.namespace = ?"
            params.append(namespace)
        query += " ORDER BY f.id DESC LIMIT 100"

        with self._connect() as conn:
            candidates = conn.execute(query, params).fetchall()

            for (
                memory_id,
                key,
                value,
                confidence,
                created_at,
                vector_json,
                source,
                source_id,
                utterance,
                ns,
            ) in candidates:
                vector: list[float] | None = None
                if vector_json:
                    try:
                        parsed = json.loads(vector_json)
                        if isinstance(parsed, list):
                            vector = [float(item) for item in parsed]
                    except (TypeError, ValueError, json.JSONDecodeError):
                        vector = None

                if vector is None:
                    document_text = f"{key}: {value}".strip()
                    vector = embed_document(document_text)
                    if vector:
                        pending_vectors.append((memory_id, json.dumps(vector)))

                if not vector:
                    continue

                base_score = _cosine_similarity(query_vector, vector)
                if base_score < semantic_threshold:
                    continue

                decayed = self._decayed_confidence(confidence, created_at)
                effective_score = base_score * decayed

                rows.append(
                    MemoryRecord(
                        key=key,
                        value=value,
                        confidence=confidence,
                        created_at=created_at,
                        id=memory_id,
                        match_type="semantic",
                        score=effective_score,
                        source=source,
                        source_id=source_id,
                        utterance=utterance,
                    )
                )

            if pending_vectors:
                now = _utc_now().isoformat()
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO memory_embeddings (memory_id, model, vector_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (memory_id, embedding_model, vector_json, now)
                        for memory_id, vector_json in pending_vectors
                    ],
                )

        rows.sort(key=lambda row: (row.score, row.id or 0), reverse=True)
        return rows

    def _build_default_embedders(
        self,
        model: str = "nomic-embed-text-v2-moe",
        keep_alive: str = "2h",
    ) -> tuple[
        Callable[[str], list[float] | None], Callable[[str], list[float] | None]
    ]:
        from ..models.embedding import OllamaEmbeddingClient

        client = OllamaEmbeddingClient(model=model)
        normalized_model = model.strip().lower().split(":", 1)[0]
        use_nomic_v2_prefixes = normalized_model == "nomic-embed-text-v2-moe"

        def _embed(text: str, prefix: str = "") -> list[float] | None:
            cleaned = text.strip()
            payload = f"{prefix}{cleaned}" if prefix and cleaned else cleaned
            result = client.embed(payload, keep_alive=keep_alive)
            return result.vector if result.ok else None

        def embed_query(text: str) -> list[float] | None:
            prefix = "search_query: " if use_nomic_v2_prefixes else ""
            return _embed(text, prefix)

        def embed_document(text: str) -> list[float] | None:
            prefix = "search_document: " if use_nomic_v2_prefixes else ""
            return _embed(text, prefix)

        return embed_query, embed_document

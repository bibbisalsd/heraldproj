"""Memory Namespaces: Structured memory with task/result and user namespaces.

This module defines structured memory namespaces with explicit write policies:

1. Hot Working Memory - Immediate contextual continuity (ephemeral, in-memory)
2. Session Short-Term Memory - Recent turns in structured form (JSONL, session-scoped)
3. User Memory - Explicit user-provided facts (SQLite, protected)
4. Task/Result Memory - Research results and completed findings (SQLite, reusable)
5. Tool Capability Memory - Tool metadata and usage policies (SQLite, static)
6. Codebase Self-Knowledge - Runtime structure and capabilities (SQLite, cached)

Key principles:
- User memory: only write on explicit statement or verified high-confidence fact
- Task memory: store results that may be referenced later
- Never let LLM invent user facts
- Confidence decay for old facts
- Full provenance tracking
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.utils.time_utils import utc_now_iso


@dataclass
class MemoryWritePolicy:
    """Policy for writing to a memory namespace."""

    namespace: str
    requires_explicit_statement: bool = False
    requires_confirmation: bool = False
    min_confidence: float = 0.75
    max_age_days: int | None = None  # None = permanent
    protected: bool = False  # Protected from casual modification


@dataclass
class MemoryReadResult:
    """Result of a memory read operation."""

    namespace: str
    key: str
    value: Any
    confidence: float
    provenance: str
    timestamp: str
    age_seconds: float
    decayed_confidence: float


# Namespace configurations
NAMESPACE_POLICIES: dict[str, MemoryWritePolicy] = {
    "hot_working": MemoryWritePolicy(
        namespace="hot_working",
        requires_explicit_statement=False,
        min_confidence=0.5,
    ),
    "session_short_term": MemoryWritePolicy(
        namespace="session_short_term",
        requires_explicit_statement=False,
        min_confidence=0.6,
        max_age_days=1,  # Session expires daily
    ),
    "user": MemoryWritePolicy(
        namespace="user",
        requires_explicit_statement=True,
        requires_confirmation=True,
        min_confidence=0.85,
        protected=True,
    ),
    "task_result": MemoryWritePolicy(
        namespace="task_result",
        requires_explicit_statement=False,
        min_confidence=0.7,
    ),
    "tool_capability": MemoryWritePolicy(
        namespace="tool_capability",
        requires_explicit_statement=False,
        min_confidence=0.9,
        protected=True,
    ),
    "codebase_self": MemoryWritePolicy(
        namespace="codebase_self",
        requires_explicit_statement=False,
        min_confidence=0.9,
        protected=True,
    ),
}


@dataclass
class HotWorkingMemory:
    """Immediate contextual continuity between turns.

    This is ephemeral, in-memory storage for:
    - Active topic
    - Active subject/entity
    - Resolved reference map
    - Last tools used
    - Last tool outputs summary
    - Active BG1 task summary
    - Active BG1 progress
    - Last BG1 result summary
    - Last route chosen
    - Last evidence packet summary
    - Likely follow-up intents
    """

    active_topic: str | None = None
    active_subject: str | None = None
    subject_aliases: list[str] = field(default_factory=list)
    resolved_reference_map: dict[str, str] = field(default_factory=dict)
    last_tools_used: list[str] = field(default_factory=list)
    last_tool_outputs_summary: str | None = None
    active_bg1_task_id: str | None = None
    active_bg1_task_subject: str | None = None
    active_bg1_progress_percent: float = 0.0
    last_bg1_result_summary: str | None = None
    last_route_chosen: str | None = None
    last_evidence_packet_summary: dict[str, Any] = field(default_factory=dict)
    likely_followup_intents: list[str] = field(default_factory=list)

    # Decay counter (increases each turn without mention)
    decay_count: int = 0
    max_decay: int = 5  # Context considered stale after N turns without mention

    def touch(self) -> None:
        """Reset decay counter."""
        self.decay_count = 0

    def decay(self) -> None:
        """Increment decay counter."""
        self.decay_count += 1

    def is_fresh(self) -> bool:
        """Check if context is still fresh."""
        return self.decay_count < self.max_decay

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "active_topic": self.active_topic,
            "active_subject": self.active_subject,
            "subject_aliases": self.subject_aliases,
            "resolved_reference_map": self.resolved_reference_map,
            "last_tools_used": self.last_tools_used,
            "last_tool_outputs_summary": self.last_tool_outputs_summary,
            "active_bg1_task_id": self.active_bg1_task_id,
            "active_bg1_task_subject": self.active_bg1_task_subject,
            "active_bg1_progress_percent": self.active_bg1_progress_percent,
            "last_bg1_result_summary": self.last_bg1_result_summary,
            "last_route_chosen": self.last_route_chosen,
            "last_evidence_packet_summary": self.last_evidence_packet_summary,
            "likely_followup_intents": self.likely_followup_intents,
            "decay_count": self.decay_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HotWorkingMemory":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class SessionTurnRecord:
    """A single turn in session short-term memory."""

    turn_id: str
    timestamp: str
    raw_text: str
    normalized_text: str
    canonical_text: str
    rewritten_routing_text: str | None = None
    intent: str | None = None
    topic: str | None = None
    subject: str | None = None
    question_type: str | None = None
    tools_used: list[str] = field(default_factory=list)
    tool_outputs_summary: str | None = None
    final_response_summary: str | None = None
    route_reasoning: str | None = None
    timing_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "canonical_text": self.canonical_text,
            "rewritten_routing_text": self.rewritten_routing_text,
            "intent": self.intent,
            "topic": self.topic,
            "subject": self.subject,
            "question_type": self.question_type,
            "tools_used": self.tools_used,
            "tool_outputs_summary": self.tool_outputs_summary,
            "final_response_summary": self.final_response_summary,
            "route_reasoning": self.route_reasoning,
            "timing_breakdown": self.timing_breakdown,
        }


@dataclass
class UserMemoryRecord:
    """A user memory fact with provenance."""

    record_id: str
    key: str
    value: str
    confidence: float
    provenance_type: str  # explicit_statement, verified_correction, confirmation_flow
    source: str | None = None
    source_id: str | None = None  # turn_id that created this memory
    utterance: str | None = None  # Original utterance
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    protected: bool = False  # Protected from modification

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "provenance_type": self.provenance_type,
            "source": self.source,
            "source_id": self.source_id,
            "utterance": self.utterance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "protected": self.protected,
        }


@dataclass
class TaskResultRecord:
    """A completed task result for future reference."""

    record_id: str
    task_id: str
    task_subject: str
    original_request: str
    result_summary: str
    facts: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    confidence: float = 0.9
    verification_strength: str = "observed"  # observed, recalled, inferred
    timestamp: str = field(default_factory=utc_now_iso)
    completed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "task_subject": self.task_subject,
            "original_request": self.original_request,
            "result_summary": self.result_summary,
            "facts": self.facts,
            "tools_used": self.tools_used,
            "confidence": self.confidence,
            "verification_strength": self.verification_strength,
            "timestamp": self.timestamp,
            "completed_at": self.completed_at,
        }


from .memory_service import MemoryService, MemoryRecord


class MemoryNamespaces:
    """Manager for structured memory namespaces.

    Provides:
    - Hot working memory (ephemeral, in-memory)
    - Session short-term memory (JSONL, session-scoped)
    - User memory (SQLite, protected)
    - Task/result memory (SQLite, reusable)
    - Tool capability memory (SQLite, static)
    - Codebase self-knowledge (SQLite, cached)
    """

    def __init__(
        self,
        memory_db_path: str | None = None,
        session_log_dir: str = "./logs/sessions",
    ) -> None:
        self.memory_db_path = memory_db_path
        self.session_log_dir = Path(session_log_dir)
        self.session_log_dir.mkdir(parents=True, exist_ok=True)

        # Persistence service
        if memory_db_path:
            self.service = MemoryService(db_path=memory_db_path)
            from jarvis.pocket_memory import PocketMemoryStore
            self.pockets = PocketMemoryStore(db_path=memory_db_path)
        else:
            self.service = None
            self.pockets = None

        # Hot working memory (in-memory)
        self.hot_working = HotWorkingMemory()

        # Session short-term memory (JSONL)
        self._session_turns: list[SessionTurnRecord] = []
        self._session_file: Path | None = None

        # Lazy-loaded/cached
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load session turns and verify service."""
        if self._loaded:
            return

        # Initialize session file for today
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._session_file = self.session_log_dir / f"session_{today}.jsonl"

        # Load existing session turns if file exists
        if self._session_file.exists():
            with open(self._session_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        self._session_turns.append(SessionTurnRecord(**data))
                    except (json.JSONDecodeError, TypeError):
                        continue

        self._loaded = True

    # ===== Hot Working Memory =====

    def get_hot_working(self) -> HotWorkingMemory:
        """Get current hot working memory state."""
        return self.hot_working

    def update_hot_working(self, **changes: Any) -> None:
        """Update hot working memory fields."""
        for key, value in changes.items():
            if hasattr(self.hot_working, key):
                setattr(self.hot_working, key, value)
        self.hot_working.touch()

    def decay_hot_working(self) -> None:
        """Decay hot working memory (call each turn without reference)."""
        self.hot_working.decay()

    def clear_hot_working(self) -> None:
        """Clear hot working memory."""
        self.hot_working = HotWorkingMemory()

    # ===== Session Short-Term Memory =====

    def add_session_turn(self, turn: SessionTurnRecord) -> None:
        """Add a turn to session short-term memory."""
        self._ensure_loaded()
        self._session_turns.append(turn)

        # Append to session file
        if self._session_file:
            with open(self._session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(turn.to_dict()) + "\n")

    def get_recent_turns(self, limit: int = 10) -> list[SessionTurnRecord]:
        """Get recent session turns."""
        self._ensure_loaded()
        return self._session_turns[-limit:]

    def search_session_turns(
        self,
        query: str,
        limit: int = 5,
    ) -> list[SessionTurnRecord]:
        """Search session turns by text content."""
        self._ensure_loaded()
        query_lower = query.lower()

        matches = []
        for turn in reversed(self._session_turns):
            if (
                query_lower in turn.raw_text.lower()
                or query_lower in turn.normalized_text.lower()
                or query_lower in (turn.final_response_summary or "").lower()
            ):
                matches.append(turn)
                if len(matches) >= limit:
                    break

        return matches

    def clear_session(self) -> None:
        """Clear session short-term memory."""
        self._session_turns = []
        self._session_file = None
        self._loaded = False

    # ===== Persistence Delegation =====

    def remember(
        self,
        key: str,
        value: str,
        confidence: float = 0.95,
        namespace: str = "user",
        source: str | None = None,
        source_id: str | None = None,
        utterance: str | None = None,
    ) -> bool:
        """Delegate remember to MemoryService."""
        if not self.service:
            return False
        return self.service.save(
            key,
            value,
            confidence,
            namespace=namespace,
            source=source,
            source_id=source_id,
            utterance=utterance,
        )

    def recall(self, key: str, namespace: str | None = None) -> list[Any]:
        """Delegate recall to MemoryService."""
        if not self.service:
            return []
        return self.service.retrieve(key, namespace=namespace)

    def owner_name(self) -> str | None:
        """Retrieve remembered owner name."""
        rows = self.recall("user_name")
        if not rows:
            return None
        return str(rows[0].value).strip()

    # ===== User Memory =====

    def write_user_memory(
        self,
        key: str,
        value: str,
        confidence: float,
        provenance_type: str,
        source_id: str | None = None,
        utterance: str | None = None,
        protected: bool = False,
    ) -> bool:
        """Write to user memory with policy enforcement.

        Args:
            key: Memory key
            value: Memory value
            confidence: Confidence score (must meet policy minimum)
            provenance_type: type of provenance (explicit_statement, etc.)
            source_id: Source ID (turn_id)
            utterance: Original utterance
            protected: Whether to protect from modification

        Returns:
            True if created or policy violated
        """
        policy = NAMESPACE_POLICIES["user"]

        # Check policy
        if (
            policy.requires_explicit_statement
            and provenance_type != "explicit_statement"
        ):
            return False
        if confidence < policy.min_confidence:
            return False

        if not self.service:
            return False

        return self.service.save(
            key=key,
            value=value,
            confidence=confidence,
            namespace="user",
            source=provenance_type,
            source_id=source_id,
            utterance=utterance,
        )

    def read_user_memory(self, key: str) -> list[MemoryRecord]:
        """Read from user memory."""
        if not self.service:
            return []
        return self.service.retrieve(key=key, namespace="user")

    def get_all_user_memory(self) -> list[MemoryRecord]:
        """Get all user memory records."""
        if not self.service:
            return []
        # Return last 100 for summary/safety
        with self.service._connect() as conn:
            rows = conn.execute(
                "SELECT id, key, value, confidence, created_at, source, source_id, utterance FROM memory_facts WHERE namespace = 'user' ORDER BY id DESC LIMIT 100"
            ).fetchall()
        return [
            MemoryRecord(
                key=r[1],
                value=r[2],
                confidence=r[3],
                created_at=r[4],
                id=r[0],
                source=r[5],
                source_id=r[6],
                utterance=r[7],
            )
            for r in rows
        ]

    def update_user_memory(
        self,
        record_id: str,
        new_value: str,
        confidence: float,
    ) -> bool:
        """Update a user memory record by ID (mapped to stable integer ID)."""
        if not self.service or not record_id.startswith("user_"):
            return False
        
        # This is a bit of a hack since MemoryService uses integer IDs
        # For now, we'll assume record_id is 'user_<int_id>'
        try:
            int_id = int(record_id.split("_")[1])
            return self.service.update_by_id(int_id, new_value, confidence)
        except (ValueError, IndexError):
            return False

    def delete_user_memory(self, record_id: str) -> bool:
        """Delete a user memory record by ID."""
        if not self.service or not record_id.startswith("user_"):
            return False
        try:
            int_id = int(record_id.split("_")[1])
            return self.service.forget_by_id(int_id)
        except (ValueError, IndexError):
            return False

    # ===== Task/Result Memory =====

    def write_task_result(
        self,
        task_id: str,
        task_subject: str,
        original_request: str,
        result_summary: str,
        facts: list[str] | None = None,
        tools_used: list[str] | None = None,
        confidence: float = 0.9,
        verification_strength: str = "observed",
    ) -> bool:
        """Write a task result to memory."""
        if not self.service:
            return False

        # Store result summary as the primary fact
        payload = {
            "task_id": task_id,
            "subject": task_subject,
            "request": original_request,
            "facts": facts or [],
            "tools": tools_used or [],
            "strength": verification_strength,
        }
        
        return self.service.save(
            key=task_subject,
            value=result_summary,
            confidence=confidence,
            namespace="task_result",
            source="bg1_worker",
            source_id=task_id,
            utterance=original_request,
        )

    def get_task_result(self, task_id: str) -> MemoryRecord | None:
        """Get a task result by task ID."""
        if not self.service:
            return None
        
        with self.service._connect() as conn:
            row = conn.execute(
                "SELECT id, key, value, confidence, created_at, source, source_id, utterance FROM memory_facts WHERE source_id = ? AND namespace = 'task_result' LIMIT 1",
                (task_id,)
            ).fetchone()
        
        if not row:
            return None
            
        return MemoryRecord(
            key=row[1],
            value=row[2],
            confidence=row[3],
            created_at=row[4],
            id=row[0],
            source=row[5],
            source_id=row[6],
            utterance=row[7],
        )

    def search_task_results(
        self,
        subject: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """Search task results by subject using semantic search."""
        if not self.service:
            return []
        
        return self.service.search(
            query=subject,
            top_k=limit,
            namespace="task_result"
        )

    def get_all_task_results(self) -> list[MemoryRecord]:
        """Get all task results (limited to 100)."""
        if not self.service:
            return []
        
        with self.service._connect() as conn:
            rows = conn.execute(
                "SELECT id, key, value, confidence, created_at, source, source_id, utterance FROM memory_facts WHERE namespace = 'task_result' ORDER BY id DESC LIMIT 100"
            ).fetchall()
            
        return [
            MemoryRecord(
                key=r[1],
                value=r[2],
                confidence=r[3],
                created_at=r[4],
                id=r[0],
                source=r[5],
                source_id=r[6],
                utterance=r[7],
            )
            for r in rows
        ]

    # ===== Retrieval with Confidence Decay =====

    def retrieve_with_decay(
        self,
        namespace: str,
        key: str,
        half_life_days: float = 30.0,
    ) -> list[MemoryReadResult]:
        """Retrieve memory with exponential confidence decay from persistent service."""
        if not self.service:
            return []
            
        # MemoryService already filters by 0.75 decayed threshold in its retrieve()
        records = self.service.retrieve(key=key, namespace=namespace)
        now = datetime.now(timezone.utc)
        
        results = []
        for r in records:
            created = datetime.fromisoformat(r.created_at)
            age_seconds = (now - created).total_seconds()
            
            # Re-calculate decay for the ReadResult structure
            age_days = age_seconds / 86400.0
            decay_factor = 0.5 ** (age_days / half_life_days)
            decayed_confidence = r.confidence * decay_factor
            
            results.append(
                MemoryReadResult(
                    namespace=namespace,
                    key=r.key,
                    value=r.value,
                    confidence=r.confidence,
                    provenance=r.source or "unknown",
                    timestamp=r.created_at,
                    age_seconds=age_seconds,
                    decayed_confidence=decayed_confidence,
                )
            )
        return results

    # ===== Utility =====

    def get_namespace_summary(self) -> dict[str, Any]:
        """Get summary of all namespaces with accurate persistent counts."""
        user_all = self.get_all_user_memory()
        task_all = self.get_all_task_results()
        
        return {
            "hot_working": self.hot_working.to_dict(),
            "session_short_term": {
                "turn_count": len(self._session_turns),
                "recent_turns": [t.to_dict() for t in self._session_turns[-5:]],
            },
            "user": {
                "record_count": len(user_all),
                "records": [r.key for r in user_all[:10]],
            },
            "task_result": {
                "record_count": len(task_all),
                "records": [r.key for r in task_all[:10]],
            },
        }

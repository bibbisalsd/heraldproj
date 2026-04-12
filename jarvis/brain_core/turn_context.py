"""TurnContextPacket: Expanded context for routing and follow-up understanding.

This module defines the structured context packet that carries contextual
information across turns, enabling follow-up resolution and intelligent routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.utils.time_utils import utc_now_iso


@dataclass
class ActiveContext:
    """Active topic and subject tracking for follow-up resolution."""

    topic: str | None = None
    subject: str | None = None
    subject_aliases: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=utc_now_iso)
    decay_count: int = 0  # Increases each turn without mention, resets on mention

    def is_fresh(self, max_decay: int = 3) -> bool:
        """Check if context is still fresh (not decayed)."""
        return self.decay_count < max_decay

    def touch(self) -> None:
        """Reset decay counter and update timestamp."""
        self.decay_count = 0
        self.last_updated = utc_now_iso()

    def decay(self) -> None:
        """Increment decay counter."""
        self.decay_count += 1


@dataclass
class ResolvedReference:
    """A single resolved vague reference."""

    original: str
    resolved: str
    confidence: float
    source: str  # context, memory, default


@dataclass
class FollowUpIntent:
    """Likely follow-up intent patterns."""

    intent_type: (
        str  # clarification, expansion, correction, result_request, progress_check
    )
    confidence: float
    trigger_phrase: str
    expected_subject: str | None = None


@dataclass
class TurnContextPacket:
    """Expanded context packet for routing and follow-up understanding.

    This packet carries structured contextual information that enables:
    - Vague reference resolution (it/that/they/why)
    - Follow-up intent detection
    - Topic continuity across turns
    - Intelligent routing based on active context

    Updated after every turn, decayed when not referenced.
    """

    # Turn identification
    turn_id: str
    timestamp: str = field(default_factory=utc_now_iso)

    # Input normalization
    raw_text: str = ""
    normalized_text: str = ""
    canonical_text: str = ""

    # Wake-word and follow-up acceptance
    wake_word_detected: bool = False
    wake_word_type: str | None = None  # explicit, fuzzy, follow-up
    follow_up_accepted: bool = False

    # Contextual rewrite (Stage 2)
    context_rewrite: str | None = None
    context_rewrite_reason: str | None = None
    resolved_references: list[ResolvedReference] = field(default_factory=list)

    # Topic and subject (for follow-up continuity)
    active_context: ActiveContext = field(default_factory=ActiveContext)

    # Question/intent classification
    intent: str | None = None
    intent_family: str | None = (
        None  # performance, bg1_update, bg1_result, website, capability, etc.
    )
    question_type: str | None = (
        None  # what, who, where, when, how, why, yes_no, command
    )
    predicate_clause: str | None = None  # The action/state being asked about

    # Route information
    route_family: str | None = (
        None  # exact, contextual, tool_first, llm_composition, bg1
    )
    chosen_route: str | None = None
    route_candidates: list[str] = field(default_factory=list)
    route_reason: str | None = None

    # Tools context
    tools_used: list[str] = field(default_factory=list)
    tool_intent_detected: bool = False
    tool_type: str | None = None  # lookup, execution, retrieval, inspection

    # Verification and confidence
    verification_strength: str = "unknown"  # observed, recalled, inferred, guessed
    confidence: float = 1.0

    # Active task linkage
    active_task_id: str | None = None
    active_task_subject: str | None = None

    # Recent facts (from last turn, for continuity)
    recent_facts: list[str] = field(default_factory=list)

    # Likely follow-up intents (predicted)
    likely_followup_intents: list[FollowUpIntent] = field(default_factory=list)

    # Memory context
    memory_retrieved: bool = False
    memory_hit_count: int = 0

    # BG1 context
    bg1_job_id: str | None = None
    bg1_state: str | None = None  # queued, running, completed, failed
    bg1_progress_percent: float = 0.0

    # Performance tracking
    latency_total_ms: float = 0.0
    latency_breakdown: dict[str, float] = field(default_factory=dict)

    # Output context
    resolved_by: str = "deterministic"  # deterministic, tool, llm, bg1
    llm_model_used: str | None = None
    spoken_text: str | None = None
    display_text: str | None = None

    # Debug trace
    debug_trace: dict[str, Any] = field(default_factory=dict)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def decay_active_context(self) -> None:
        """Decay active context when not referenced."""
        self.active_context.decay()

    def refresh_active_context(
        self,
        topic: str | None,
        subject: str | None,
        aliases: list[str] | None = None,
    ) -> None:
        """Refresh active context with new topic/subject."""
        if topic or subject:
            self.active_context = ActiveContext(
                topic=topic or self.active_context.topic,
                subject=subject or self.active_context.subject,
                subject_aliases=aliases or [],
            )

    def add_resolved_reference(
        self,
        original: str,
        resolved: str,
        confidence: float,
        source: str,
    ) -> None:
        """Add a resolved reference to the packet."""
        self.resolved_references.append(
            ResolvedReference(
                original=original,
                resolved=resolved,
                confidence=confidence,
                source=source,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "canonical_text": self.canonical_text,
            "wake_word_detected": self.wake_word_detected,
            "wake_word_type": self.wake_word_type,
            "follow_up_accepted": self.follow_up_accepted,
            "context_rewrite": self.context_rewrite,
            "context_rewrite_reason": self.context_rewrite_reason,
            "resolved_references": [
                {
                    "original": r.original,
                    "resolved": r.resolved,
                    "confidence": r.confidence,
                    "source": r.source,
                }
                for r in self.resolved_references
            ],
            "active_context": {
                "topic": self.active_context.topic,
                "subject": self.active_context.subject,
                "subject_aliases": self.active_context.subject_aliases,
                "last_updated": self.active_context.last_updated,
                "decay_count": self.active_context.decay_count,
            },
            "intent": self.intent,
            "intent_family": self.intent_family,
            "question_type": self.question_type,
            "predicate_clause": self.predicate_clause,
            "route_family": self.route_family,
            "chosen_route": self.chosen_route,
            "route_candidates": self.route_candidates,
            "route_reason": self.route_reason,
            "tools_used": self.tools_used,
            "tool_intent_detected": self.tool_intent_detected,
            "tool_type": self.tool_type,
            "verification_strength": self.verification_strength,
            "confidence": self.confidence,
            "active_task_id": self.active_task_id,
            "active_task_subject": self.active_task_subject,
            "recent_facts": self.recent_facts,
            "likely_followup_intents": [
                {
                    "intent_type": i.intent_type,
                    "confidence": i.confidence,
                    "trigger_phrase": i.trigger_phrase,
                    "expected_subject": i.expected_subject,
                }
                for i in self.likely_followup_intents
            ],
            "memory_retrieved": self.memory_retrieved,
            "memory_hit_count": self.memory_hit_count,
            "bg1_job_id": self.bg1_job_id,
            "bg1_state": self.bg1_state,
            "bg1_progress_percent": self.bg1_progress_percent,
            "latency_total_ms": self.latency_total_ms,
            "latency_breakdown": self.latency_breakdown,
            "resolved_by": self.resolved_by,
            "llm_model_used": self.llm_model_used,
            "spoken_text": self.spoken_text,
            "display_text": self.display_text,
            "debug_trace": self.debug_trace,
            "metadata": self.metadata,
        }

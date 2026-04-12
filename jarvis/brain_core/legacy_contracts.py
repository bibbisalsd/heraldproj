"""Deprecated merger artifact — not used by runtime. (P3-3)"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from jarvis.utils.time_utils import utc_now_iso

# Import dependencies for types
from .contracts import (
    ReferenceResolution,
    MemoryHit,
    ToolPlanItem,
    ToolOutput,
    EvidencePacketSummary,
    LatencyBreakdown,
)

@dataclass
class TurnArtifact:
    """Extended TurnArtifact with richer fields (Esoteric v0.2 version).

    WARNING: This is NOT the version used by the runtime pipeline.
    CANONICAL version: jarvis.brain_core.contracts.TurnArtifact (30 fields)
    This version (42 fields) is the Esoteric-side definition from the merger.
    It is exported by brain_core/__init__.py for backward compatibility but
    the turn_pipeline.py and runtime_v2.py use the contracts.py version.

    Planned: consolidate these two definitions into one canonical class.
    """

    # Identification
    turn_id: str
    source: str  # voice, text, addon, bg1_callback, tool_callback
    channel_id: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)
    created_at: str = field(default_factory=utc_now_iso)

    # Input stages
    raw_text: str = ""
    normalized_text: str = ""
    canonical_text: str = ""

    # Contextual rewrite (Stage 2)
    context_rewrite: str | None = None
    context_rewrite_reason: str | None = None
    reference_resolutions: list[ReferenceResolution] = field(default_factory=list)

    # Understanding (Stage 3-4)
    intent: str | None = None
    route_candidates: list[str] = field(default_factory=list)
    chosen_route: str | None = None
    route_reason: str | None = None

    # Topic/subject extraction
    topic: str | None = None
    subject: str | None = None
    subject_aliases: list[str] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    question_type: str | None = (
        None  # what, who, where, when, how, why, yes_no, command
    )

    # Memory retrieval (Stage 3)
    memory_hits: list[MemoryHit] = field(default_factory=list)

    # Tool planning and execution (Stage 5-6)
    tools_planned: list[ToolPlanItem] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    tool_outputs: list[ToolOutput] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)

    # Job/BG1 context
    job_id: str | None = None
    job_snapshot: dict[str, Any] | None = None

    # Evidence packet (Stage 5)
    evidence_packet_summary: EvidencePacketSummary | None = None
    evidence_summary: str = ""

    # Response generation (Stage 7)
    llm_used: bool = False
    llm_model: str | None = None
    resolved_by: str = "deterministic"  # deterministic, tool, llm, bg1

    # Output (Stage 8)
    spoken_text: str | None = None
    display_text: str | None = None
    debug_trace: dict[str, Any] = field(default_factory=dict)

    # Latency tracking (Stage 14)
    latency_breakdown: LatencyBreakdown = field(default_factory=LatencyBreakdown)

    # Confidence and quality
    confidence: float = 1.0

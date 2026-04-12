from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from jarvis.utils.time_utils import utc_now_iso


@dataclass(frozen=True)
class RawEvent:
    source: str
    speaker_id: str
    channel: str
    payload: str
    timestamp: str = field(default_factory=utc_now_iso)
    addon_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngressEnvelope:
    turn_id: str
    source: str
    text: str
    profile: str
    created_at: str = field(default_factory=utc_now_iso)
    addon_id: Optional[str] = None
    channel_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_raw(raw: RawEvent, profile: str = "owner") -> "IngressEnvelope":
        return IngressEnvelope(
            turn_id=f"turn-{uuid4().hex[:12]}",
            source=raw.source,
            text=raw.payload.strip(),
            profile=profile,
            addon_id=raw.addon_id,
            channel_id=raw.channel,
            metadata=dict(raw.metadata),
        )

    def replace(self, **changes: Any) -> "IngressEnvelope":
        return replace(self, **changes)


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_ms: int
    reason: str


@dataclass(frozen=True)
class MemoryInfo:
    """Structured memory information for the evidence packet."""

    memory_type: str  # user, task_result, hot_working, session
    key: str
    value: str
    confidence: float
    provenance: str
    timestamp: str


@dataclass(frozen=True)
class TaskInfo:
    """Information about an active or completed BG1 task."""

    task_id: str
    subject: str
    original_request: str
    state: str  # running, completed, failed
    progress_percent: float
    result_summary: str | None = None
    tools_used: list[str] = field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class VerifiedFact:
    """A single verified fact with provenance."""

    content: str
    source: str  # tool, memory, observation, inference
    confidence: float
    timestamp: str
    verification_strength: str  # observed, recalled, inferred, guessed


@dataclass(frozen=True)
class LLMDerivedResult:
    """A result derived from an LLM rather than deterministic verification."""

    content: str
    source: str
    model: str
    confidence: float = 0.7
    timestamp: str = ""
    verification_strength: str = "inferred"


@dataclass(frozen=True)
class TaggedFact:
    """A fact with explicit verification strength tagging."""

    content: str
    strength: str  # observed, recalled, inferred, guessed
    source: str = "provided"
    confidence: float = 0.95


@dataclass(frozen=True)
class StylePolicy:
    """Output style constraints for the LLM."""

    tone: str  # helpful, concise, technical, casual
    length_hint: str  # short, medium, long
    spoken_friendly: bool
    avoid_internal_ids: bool
    address_preference: str | None = None  # e.g., "sir", "mate", or None


@dataclass(frozen=True)
class EvidencePacket:
    """Strict structured packet of verified/contextualized information.

    This packet contains ONLY verified facts and context that the LLM
    can use to compile a response. The LLM cannot:
    - Add new facts not in this packet
    - Call tools (tools are called by the brain before packet assembly)
    - Make claims without evidence backing
    - Guess or hallucinate information

    If the packet lacks sufficient information, the LLM should ask
    a clarifying question instead of fabricating an answer.
    """

    # Core user input
    latest_user_message: str
    resolved_intent: str

    # Context resolution
    active_topic: str | None = None
    active_subject: str | None = None
    resolved_reference_map: dict[str, str] = field(default_factory=dict)

    # Memory context
    memory_info: list[MemoryInfo] = field(default_factory=list)

    # Previous message context (for follow-up understanding)
    previous_message_context: str | None = None

    # Active task context
    task_info: TaskInfo | None = None

    # Tool execution results
    tools_used: list[str] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)

    # Verified facts (the core content the LLM can use)
    verified_facts: list[VerifiedFact | LLMDerivedResult] = field(default_factory=list)

    # Inference policy (how the LLM should reason)
    inference_policy: str = "evidence_only"  # evidence_only, evidence_plus_inference

    # Style policy (how the LLM should phrase the response)
    style_policy: StylePolicy = field(
        default_factory=lambda: StylePolicy(
            tone="helpful",
            length_hint="short",
            spoken_friendly=True,
            avoid_internal_ids=True,
        )
    )

    # Constraints (hard rules the LLM must follow)
    constraints: list[str] = field(
        default_factory=lambda: [
            "ONLY use information provided in this packet",
            "DO NOT add facts not present here",
            "DO NOT call tools",
            "If information is insufficient, ask ONE short clarifying question",
            "DO NOT state internal resource headings or labels",
        ]
    )

    def to_prompt_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for prompt assembly."""
        return {
            "latest_user_message": self.latest_user_message,
            "resolved_intent": self.resolved_intent,
            "active_topic": self.active_topic,
            "active_subject": self.active_subject,
            "resolved_reference_map": self.resolved_reference_map,
            "memory_info": [
                {
                    "memory_type": m.memory_type,
                    "key": m.key,
                    "value": m.value,
                    "confidence": m.confidence,
                    "provenance": m.provenance,
                    "timestamp": m.timestamp,
                }
                for m in self.memory_info
            ],
            "previous_message_context": self.previous_message_context,
            "task_info": (
                {
                    "task_id": self.task_info.task_id,
                    "subject": self.task_info.subject,
                    "original_request": self.task_info.original_request,
                    "state": self.task_info.state,
                    "progress_percent": self.task_info.progress_percent,
                    "result_summary": self.task_info.result_summary,
                    "tools_used": self.task_info.tools_used,
                }
                if self.task_info
                else None
            ),
            "tools_used": self.tools_used,
            "tool_results": self.tool_results,
            "verified_facts": [
                {
                    "content": f.content,
                    "source": f.source,
                    "confidence": f.confidence,
                    "verification_strength": f.verification_strength,
                }
                for f in self.verified_facts
            ],
            "inference_policy": self.inference_policy,
            "style_policy": {
                "tone": self.style_policy.tone,
                "length_hint": self.style_policy.length_hint,
                "spoken_friendly": self.style_policy.spoken_friendly,
                "address_preference": self.style_policy.address_preference,
            },
            "constraints": self.constraints,
        }

    def to_prompt_text(self) -> str:
        """Convert to text format suitable for LLM prompt.

        This produces the structured prompt that instructs the LLM
        to compile from evidence only.
        """
        sections = []

        # Opening instruction
        sections.append("ONLY USE THIS INFORMATION TO COMPILE YOUR ANSWER.")
        sections.append(
            "COMPILE YOUR ANSWER IN A SHORT, INFORMATIVE, NATURAL, SPOKEN WAY."
        )
        sections.append("DO NOT STATE THE RESOURCE HEADINGS OR INTERNAL RESOURCES.")
        sections.append(
            "IF THE INFORMATION IS INSUFFICIENT, ASK ONE SHORT CLARIFYING QUESTION."
        )
        sections.append("")

        # Memory info
        if self.memory_info:
            sections.append("MEMORY INFO:")
            for m in self.memory_info:
                sections.append(f"  - [{m.memory_type}] {m.key}: {m.value}")
            sections.append("")

        # Tool info
        if self.tools_used or self.tool_results:
            sections.append("TOOLS USED:")
            for tool in self.tools_used:
                sections.append(f"  - {tool}")
            if self.tool_results:
                sections.append("TOOL RESULTS:")
                for result in self.tool_results:
                    sections.append(f"  - {result}")
            sections.append("")

        # Previous message context
        if self.previous_message_context:
            sections.append("PREVIOUS MESSAGE CONTEXT:")
            sections.append(f"  {self.previous_message_context}")
            sections.append("")

        # Task info
        if self.task_info:
            sections.append("TASK INFO:")
            sections.append(f"  Subject: {self.task_info.subject}")
            sections.append(
                f"  State: {self.task_info.state} ({self.task_info.progress_percent}% complete)"
            )
            if self.task_info.result_summary:
                sections.append(f"  Result: {self.task_info.result_summary}")
            sections.append("")

        # Verified facts
        if self.verified_facts:
            sections.append("VERIFIED FACTS:")
            for f in self.verified_facts:
                sections.append(f"  [{f.verification_strength}] {f.content}")
            sections.append("")

        # Reference resolution
        if self.resolved_reference_map:
            sections.append("REFERENCE RESOLUTION:")
            for original, resolved in self.resolved_reference_map.items():
                sections.append(f"  {original} -> {resolved}")
            sections.append("")

        # Style policy
        sections.append("STYLE POLICY:")
        sections.append(f"  Tone: {self.style_policy.tone}")
        sections.append(f"  Length: {self.style_policy.length_hint}")
        if self.style_policy.address_preference:
            sections.append(f"  Address as: {self.style_policy.address_preference}")
        sections.append("")

        # Join sections
        return "\n".join(sections)


@dataclass
class LatencyBreakdown:
    """Per-stage timing metrics for a turn."""

    stt_ms: float = 0.0
    normalize_ms: float = 0.0
    context_resolve_ms: float = 0.0
    route_ms: float = 0.0
    memory_ms: float = 0.0
    tool_plan_ms: float = 0.0
    tool_exec_ms: float = 0.0
    llm_ms: float = 0.0
    renderer_ms: float = 0.0
    tts_prep_ms: float = 0.0
    tts_speak_ms: float = 0.0
    total_ms: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "stt_ms": self.stt_ms,
            "normalize_ms": self.normalize_ms,
            "context_resolve_ms": self.context_resolve_ms,
            "route_ms": self.route_ms,
            "memory_ms": self.memory_ms,
            "tool_plan_ms": self.tool_plan_ms,
            "tool_exec_ms": self.tool_exec_ms,
            "llm_ms": self.llm_ms,
            "renderer_ms": self.renderer_ms,
            "tts_prep_ms": self.tts_prep_ms,
            "tts_speak_ms": self.tts_speak_ms,
            "total_ms": self.total_ms,
        }


@dataclass
class ReferenceResolution:
    """Resolved vague references like it/that/they/why."""

    original_phrase: str
    resolved_reference: str
    resolution_reason: str
    confidence: float = 1.0


@dataclass(frozen=True)
class MemoryResult:
    """Unified memory retrieval result."""
    key: str
    value: str
    confidence: float
    namespace: str  # user, task_result, hot_working, session, codebase
    provenance: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryHit:
    """A single memory retrieval result (Legacy)."""
    memory_type: str  # maps to namespace
    key: str
    value: str
    confidence: float
    provenance: str
    age_seconds: float = 0.0



@dataclass
class ToolPlanItem:
    """A planned tool invocation."""

    tool_name: str
    purpose: str
    inputs: dict[str, Any]
    lane: str  # realtime or bg1
    reason: str


@dataclass
class ToolOutput:
    """Result of a tool execution."""

    tool_name: str
    ok: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    verification_strength: str = "observed"  # observed, recalled, inferred, guessed


@dataclass
class EvidencePacketSummary:
    """Summary of the evidence packet sent to the LLM."""

    latest_user_message: str
    resolved_intent: str
    active_topic: str | None = None
    active_subject: str | None = None
    reference_map: dict[str, str] = field(default_factory=dict)
    memory_info_count: int = 0
    previous_message_context: str | None = None
    task_info: str | None = None
    tools_used: list[str] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    verified_facts_count: int = 0
    inference_policy: str = "evidence_only"


@dataclass
class TurnArtifact:
    """Canonical TurnArtifact used by the runtime pipeline."""

    turn_id: str
    source: str
    raw_text: str = ""
    normalized_text: str = ""
    canonical_text: str = ""
    context_rewrite: str = ""
    context_rewrite_reason: str = ""
    resolved_reference_map: dict[str, str] = field(default_factory=dict)
    intent: str = ""
    route_candidates: list[str] = field(default_factory=list)
    chosen_route: str = ""
    topic: str = ""
    subject: str | None = None
    entities: list[dict[str, Any]] = field(default_factory=list)
    question_type: str = ""
    memory_hits: list[str] = field(default_factory=list)
    tools_planned: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)
    job_snapshot: dict[str, Any] = field(default_factory=dict)
    evidence_summary: str = ""
    evidence_packet: EvidencePacket | None = None
    llm_used: str = ""
    resolved_by: str = ""
    spoken_text: str = ""
    display_text: str = ""
    latency_breakdown: LatencyBreakdown = field(default_factory=LatencyBreakdown)
    confidence: float = 0.0
    writebacks: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "turn_id": self.turn_id,
            "source": self.source,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "canonical_text": self.canonical_text,
            "context_rewrite": self.context_rewrite,
            "context_rewrite_reason": self.context_rewrite_reason,
            "intent": self.intent,
            "chosen_route": self.chosen_route,
            "topic": self.topic,
            "subject": self.subject,
            "tools_used": self.tools_used,
            "tool_summaries": self.tool_summaries,
            "llm_used": self.llm_used,
            "resolved_by": self.resolved_by,
            "spoken_text": self.spoken_text,
            "display_text": self.display_text,
            "latency_breakdown": self.latency_breakdown.to_dict(),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ToolResultEnvelope:

    ok: bool
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    safety_flags: List[str] = field(default_factory=list)
    elapsed_ms: int = 0


@dataclass(frozen=True)
class RenderPacket:
    facts: List[str]
    constraints: List[str]
    tone: str
    length_hint: str
    max_packet_tokens: int = 384


@dataclass(frozen=True)
class RenderedReply:
    text: str
    sink: str = "local_voice"
    route_hint: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobStatus:
    """Legacy JobStatus for contracts/event payloads.

    CANONICAL version: jarvis.world_model.task.JobStatus
    (used by WorldState, state_builder — has different fields: task_id, progress, etc.).
    This version is used by brain_core/__init__.py exports and event records.
    """

    job_id: str
    stage: str
    status: str
    percent: float
    eta: Optional[str]
    last_update: str = field(default_factory=utc_now_iso)
    errors: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AddonManifest:
    addon_id: str
    addon_name: str
    version: str
    enabled_by_default: bool = False
    safe_in_degraded_mode: bool = False
    tools: Tuple[str, ...] = ()
    input_bridges: Tuple[str, ...] = ()
    output_sinks: Tuple[str, ...] = ()
    audio_channels: Tuple[str, ...] = ()
    required_permissions: Tuple[str, ...] = ()
    startup_hook: Optional[str] = None
    shutdown_hook: Optional[str] = None
    healthcheck_hook: Optional[str] = None
    config_schema: Dict[str, Any] = field(default_factory=dict)
    command_pack: Tuple[str, ...] = ()
    permission_mapper: Optional[str] = None
    capability_summary: str = ""


REQUIRED_MANIFEST_FIELDS = (
    "addon_id",
    "addon_name",
    "version",
)


def validate_manifest(manifest: AddonManifest) -> List[str]:
    errors: List[str] = []
    for field_name in REQUIRED_MANIFEST_FIELDS:
        if not getattr(manifest, field_name, None):
            errors.append(f"missing_{field_name}")
    if not manifest.capability_summary:
        errors.append("missing_capability_summary")
    return errors


ALLOWED_CALL_GRAPH = {
    ("ingress_hub", "ingress_normalizer"),
    ("ingress_normalizer", "lane_coordinator"),
    ("lane_coordinator", "realtime_lane"),
    ("lane_coordinator", "bg1_queue"),
    ("bg1_queue", "bg1_worker"),
    ("realtime_lane", "tool_orchestrator"),
    ("bg1_worker", "tool_orchestrator"),
    ("tool_orchestrator", "output_coordinator"),
    ("memory_service", "sqlite"),
    ("addon_audio_pipeline", "ingress_hub"),
    ("addon_manager", "addon_registry"),
}


def is_call_allowed(source: str, target: str) -> bool:
    return (source, target) in ALLOWED_CALL_GRAPH


def assert_allowed_calls(edges: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    blocked: List[Tuple[str, str]] = []
    for edge in edges:
        if edge not in ALLOWED_CALL_GRAPH:
            blocked.append(edge)
    return blocked

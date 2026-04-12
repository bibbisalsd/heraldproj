"""Brain core compartments and contracts."""

from __future__ import annotations


# Core contracts — TurnArtifact lives here (the pipeline's canonical version)
from .contracts import (
    RawEvent,
    IngressEnvelope,
    RetryDecision,
    TurnArtifact,
    ToolResultEnvelope,
    RenderPacket,
    RenderedReply,
    JobStatus,
    AddonManifest,
    validate_manifest,
    is_call_allowed,
    assert_allowed_calls,
)

# Turn processing helpers (supplementary dataclasses from contracts.py)
from .contracts import (
    LatencyBreakdown,
    ReferenceResolution,
    MemoryHit,
    ToolPlanItem,
    ToolOutput,
    EvidencePacketSummary,
)
from .turn_context import (
    TurnContextPacket,
    ActiveContext,
    ResolvedReference,
    FollowUpIntent,
)
from .contracts import (
    EvidencePacket,
    MemoryInfo,
    TaskInfo,
    VerifiedFact,
    StylePolicy,
)
from .reference_resolver import ReferenceResolver, resolve_references, ContextualRewrite

# BG1 narration
from .bg1_narrator import (
    BG1Narrator,
    NarrationStyle,
    NarrationResult,
    narrate_start,
    narrate_progress,
    narrate_completion,
    narrate_error,
)

# Debug trace
from .debug_trace import (
    DebugTraceLogger,
    TraceRecord,
    DebugLevel,
    get_logger,
    log_turn_start,
    log_turn_end,
    log_turn_summary,
)

# Tool policy
from .tool_policy import (
    ToolPolicy,
    ToolMetadata,
    ToolResult,
    LanePolicy,
    VerificationStrength,
    LatencyClass,
)

# Memory namespaces
from .memory_namespaces import (
    MemoryNamespaces,
    HotWorkingMemory,
    SessionTurnRecord,
    UserMemoryRecord,
    TaskResultRecord,
    MemoryWritePolicy,
    NAMESPACE_POLICIES,
)

__all__ = [
    # Core contracts
    "RawEvent",
    "IngressEnvelope",
    "RetryDecision",
    "ToolResultEnvelope",
    "RenderPacket",
    "RenderedReply",
    "JobStatus",
    "AddonManifest",
    "validate_manifest",
    "is_call_allowed",
    "assert_allowed_calls",
    # Turn processing
    "TurnArtifact",
    "LatencyBreakdown",
    "ReferenceResolution",
    "MemoryHit",
    "ToolPlanItem",
    "ToolOutput",
    "EvidencePacketSummary",
    "EvidencePacket",
    "MemoryInfo",
    "TaskInfo",
    "VerifiedFact",
    "StylePolicy",
    "TurnContextPacket",
    "ActiveContext",
    "ResolvedReference",
    "FollowUpIntent",
    "ReferenceResolver",
    "resolve_references",
    "ContextualRewrite",
    # BG1 narration
    "BG1Narrator",
    "NarrationStyle",
    "NarrationResult",
    "narrate_start",
    "narrate_progress",
    "narrate_completion",
    "narrate_error",
    # Debug trace
    "DebugTraceLogger",
    "TraceRecord",
    "DebugLevel",
    "get_logger",
    "log_turn_start",
    "log_turn_end",
    "log_turn_summary",
    # Tool policy
    "ToolPolicy",
    "ToolMetadata",
    "ToolResult",
    "LanePolicy",
    "VerificationStrength",
    "LatencyClass",
    # Memory namespaces
    "MemoryNamespaces",
    "HotWorkingMemory",
    "SessionTurnRecord",
    "UserMemoryRecord",
    "TaskResultRecord",
    "MemoryWritePolicy",
    "NAMESPACE_POLICIES",
]

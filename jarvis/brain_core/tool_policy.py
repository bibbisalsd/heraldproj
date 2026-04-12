"""Tool Policy: Lane-aware tool registry with structured metadata.

This module defines the enhanced tool registry that includes:
- Lane policy (realtime vs BG1)
- Verification strength
- Latency class
- Domain tags
- Voice-friendly output policies

Key principles:
- Tools should be available in realtime when lightweight
- BG1 only for long-running or multi-step work
- Each tool declares its safety, latency, and output characteristics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class LanePolicy(str, Enum):
    """Lane assignment policy for tools."""

    REALTIME = "realtime"  # Safe for synchronous execution (<500ms expected)
    BG1 = "bg1"  # Must run in background worker (>500ms or multi-step)
    EITHER = "either"  # Can run in either lane based on context


class VerificationStrength(str, Enum):
    """Verification strength for tool results."""

    OBSERVED = "observed"  # Direct observation (file read, API response)
    COMPUTED = "computed"  # Computed from observed data (calculation, transformation)
    INFERRED = "inferred"  # Inferred from observations (analysis, summary)
    GUESSED = "guessed"  # Model-generated without evidence backing


class LatencyClass(str, Enum):
    """Expected latency class for tools."""

    FAST = "fast"  # <100ms
    MODERATE = "moderate"  # 100-500ms
    SLOW = "slow"  # 500-2000ms
    VERY_SLOW = "very_slow"  # >2000ms (should use BG1)


@dataclass
class ToolMetadata:
    """Structured metadata for a registered tool.

    This metadata enables:
    - Lane-aware routing (realtime vs BG1)
    - Voice-friendly output formatting
    - Safety and confirmation policies
    - Debug trace and observability
    """

    # Basic info
    tool_name: str
    purpose: str  # One-line description of what the tool does

    # Schema
    input_schema: dict[str, Any] = field(default_factory=dict)  # JSON schema for inputs
    example_queries: list[str] = field(
        default_factory=list
    )  # Example natural language queries

    # Lane policy
    lane_policy: LanePolicy = LanePolicy.EITHER
    safe_in_realtime: bool = True  # Explicit override for lane_policy
    safe_in_bg1: bool = True

    # Output characteristics
    voice_friendly_result_policy: str = "direct"  # direct, summarize, hide_details
    result_summary_template: str | None = None  # Optional template for voice summary

    # Verification
    verification_strength: VerificationStrength = VerificationStrength.OBSERVED

    # Latency
    latency_class: LatencyClass = LatencyClass.MODERATE
    expected_max_ms: float = 500.0

    # Safety
    requires_confirmation: bool = False
    confirmation_action: str | None = None
    capability: str | None = None  # Required capability (owner, trusted, guest)

    # Domain tags for routing
    domain_tags: list[str] = field(default_factory=list)

    # Trust
    trust_level: float = 0.9  # 0.0-1.0, default high for built-in tools

    # Platform availability
    platform_available: bool = True  # Can be disabled for Windows-only tools on Linux

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "purpose": self.purpose,
            "input_schema": self.input_schema,
            "example_queries": self.example_queries,
            "lane_policy": self.lane_policy.value,
            "safe_in_realtime": self.safe_in_realtime,
            "safe_in_bg1": self.safe_in_bg1,
            "voice_friendly_result_policy": self.voice_friendly_result_policy,
            "result_summary_template": self.result_summary_template,
            "verification_strength": self.verification_strength.value,
            "latency_class": self.latency_class.value,
            "expected_max_ms": self.expected_max_ms,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_action": self.confirmation_action,
            "capability": self.capability,
            "domain_tags": self.domain_tags,
            "trust_level": self.trust_level,
            "platform_available": self.platform_available,
        }


@dataclass
class ToolResult:
    """Enhanced tool result with metadata."""

    tool_name: str
    ok: bool
    data: Any
    summary: str
    elapsed_ms: float
    verification_strength: VerificationStrength
    lane_used: str  # realtime or bg1
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "ok": self.ok,
            "data": self.data,
            "summary": self.summary,
            "elapsed_ms": self.elapsed_ms,
            "verification_strength": self.verification_strength.value,
            "lane_used": self.lane_used,
            "error": self.error,
            "metadata": self.metadata,
        }


class ToolPolicy:
    """Policy manager for tool registration and routing.

    The ToolPolicy:
    1. Registers tools with structured metadata
    2. Provides lane-aware routing decisions
    3. Enforces safety and confirmation policies
    4. Generates voice-friendly summaries
    """

    def __init__(self, orchestrator=None) -> None:
        self._orchestrator = orchestrator

    def register_tool(
        self,
        name: str,
        fn: Callable,
        *,
        purpose: str,
        input_schema: dict[str, Any] | None = None,
        example_queries: list[str] | None = None,
        lane_policy: LanePolicy = LanePolicy.EITHER,
        safe_in_realtime: bool = True,
        safe_in_bg1: bool = True,
        voice_friendly_result_policy: str = "direct",
        result_summary_template: str | None = None,
        verification_strength: VerificationStrength = VerificationStrength.OBSERVED,
        latency_class: LatencyClass = LatencyClass.MODERATE,
        expected_max_ms: float = 500.0,
        requires_confirmation: bool = False,
        confirmation_action: str | None = None,
        capability: str | None = None,
        domain_tags: list[str] | None = None,
        trust_level: float = 0.9,
    ) -> None:
        """Register a tool with structured metadata.

        Args:
            name: Tool name
            fn: Tool function
            purpose: One-line description
            input_schema: JSON schema for inputs
            example_queries: Example natural language queries
            lane_policy: Lane assignment policy
            safe_in_realtime: Whether safe for synchronous execution
            safe_in_bg1: Whether safe for background execution
            voice_friendly_result_policy: How to format for voice output
            result_summary_template: Template for voice summary
            verification_strength: Verification strength of results
            latency_class: Expected latency class
            expected_max_ms: Expected maximum latency in ms
            requires_confirmation: Whether confirmation is required
            confirmation_action: Confirmation action type
            capability: Required capability level
            domain_tags: Domain tags for routing
            trust_level: Trust level (0.0-1.0)
        """
        self._orchestrator._tools[name] = fn
        self._orchestrator.get_all_metadata()[name] = ToolMetadata(
            tool_name=name,
            purpose=purpose,
            input_schema=input_schema or {},
            example_queries=example_queries or [],
            lane_policy=lane_policy,
            safe_in_realtime=safe_in_realtime,
            safe_in_bg1=safe_in_bg1,
            voice_friendly_result_policy=voice_friendly_result_policy,
            result_summary_template=result_summary_template,
            verification_strength=verification_strength,
            latency_class=latency_class,
            expected_max_ms=expected_max_ms,
            requires_confirmation=requires_confirmation,
            confirmation_action=confirmation_action,
            capability=capability,
            domain_tags=domain_tags or [],
            trust_level=trust_level,
        )

    def get_metadata(self, name: str) -> ToolMetadata | None:
        """Get metadata for a tool."""
        return self._orchestrator.get_all_metadata().get(name)

    def get_function(self, name: str) -> Callable | None:
        """Get the tool function."""
        return self._orchestrator._tools.get(name)

    def should_use_realtime(self, tool_name: str, context: dict | None = None) -> bool:
        """Determine if a tool should run in realtime lane.

        Args:
            tool_name: Tool name
            context: Optional context (e.g., current load, user preference)

        Returns:
            True if tool should run in realtime lane
        """
        meta = self._orchestrator.get_all_metadata().get(tool_name)
        if not meta:
            return True  # Default to realtime for unknown tools

        # Explicit overrides
        if not meta.safe_in_realtime:
            return False
        if not meta.safe_in_bg1:
            return True

        # Lane policy
        lane_policy = getattr(meta, "lane_policy", None)
        if lane_policy == LanePolicy.REALTIME:
            return True
        if lane_policy == LanePolicy.BG1:
            return False

        # EITHER: use context to decide
        if context:
            # If system is under load, prefer BG1 for slow tools
            if context.get("system_load", 0.0) > 0.8:
                latency_class = getattr(meta, "latency_class", None)
                if latency_class in (LatencyClass.SLOW, LatencyClass.VERY_SLOW):
                    return False

        # Default: realtime for fast tools
        latency_class = getattr(meta, "latency_class", None)
        return latency_class in (LatencyClass.FAST, LatencyClass.MODERATE)

    def get_voice_summary(
        self,
        tool_name: str,
        result: Any,
        elapsed_ms: float,
    ) -> str:
        """Generate voice-friendly summary of tool result.

        Args:
            tool_name: Tool name
            result: Tool result data
            elapsed_ms: Execution time

        Returns:
            Voice-friendly summary string
        """
        meta = self._orchestrator.get_all_metadata().get(tool_name)
        if not meta:
            return f"Tool {tool_name} completed in {elapsed_ms:.0f} milliseconds"

        policy = meta.voice_friendly_result_policy

        if policy == "direct":
            # Return result as-is if it's a string, otherwise summarize
            if isinstance(result, str):
                return result[:200]  # Truncate long results
            return f"{tool_name} returned: {str(result)[:100]}"

        elif policy == "summarize":
            # Use template if available
            if meta.result_summary_template:
                try:
                    return meta.result_summary_template.format(
                        result=result, elapsed_ms=elapsed_ms
                    )
                except (KeyError, ValueError):
                    pass
            return f"Completed {tool_name} in {elapsed_ms:.0f} milliseconds"

        elif policy == "hide_details":
            # Don't expose internal details
            return f"Done. {tool_name} completed."

        return str(result)[:100]

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools with metadata."""
        return [
            meta.to_dict() for meta in self._orchestrator.get_all_metadata().values()
        ]

    def get_tools_by_domain(self, domain: str) -> list[ToolMetadata]:
        """Get all tools tagged with a domain."""
        return [
            meta
            for meta in self._orchestrator.get_all_metadata().values()
            if domain in meta.domain_tags
        ]

    def get_realtime_tools(self) -> list[str]:
        """Get all tools safe for realtime execution."""
        return [
            name
            for name, meta in self._orchestrator.get_all_metadata().items()
            if meta.safe_in_realtime
        ]

    def get_bg1_tools(self) -> list[str]:
        """Get all tools that should run in BG1."""
        return [
            name
            for name, meta in self._orchestrator.get_all_metadata().items()
            if getattr(meta, "lane_policy", None) == LanePolicy.BG1
            or not getattr(meta, "safe_in_realtime", True)
        ]

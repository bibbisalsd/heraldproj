"""Tool Router: Tool-first routing with ToolPolicy consultation.

Implements the plan's layered routing philosophy:
  1. Exact match (deterministic)
  2. Contextual match (reference resolver)
  3. Tool-first match (can a registered tool handle this?)
  4. LLM fallback
  5. BG1 heavy task

The ToolRouter specifically handles step 3: given a query,
check if any registered tool can answer it directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tool_policy import ToolPolicy
from .admission_control import AdmissionControl
from .prompt_dispatcher import TaskClassifier


@dataclass(frozen=True)
class RouteCandidate:
    """A single routing candidate with a confidence score."""

    lane: str  # realtime, bg1
    intent: str  # Matched intent or tool name
    source: str  # exact, deterministic, tool_first, semantic, classifier
    confidence: float  # 0.0-1.0
    reason: str  # Human-readable routing reason
    tool_name: str | None = None  # Tool to invoke (if tool_first)
    latency_class: str = "moderate"


@dataclass
class RouteTrace:
    """Trace of all candidates considered during routing."""

    query: str
    candidates: list[RouteCandidate] = field(default_factory=list)
    selected: RouteCandidate | None = None
    elapsed_ms: float = 0.0

    def add(self, candidate: RouteCandidate) -> None:
        self.candidates.append(candidate)

    def select_best(self) -> RouteCandidate | None:
        """Select the highest-confidence candidate."""
        if not self.candidates:
            return None
        best = max(self.candidates, key=lambda c: c.confidence)
        self.selected = best
        return best

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query[:100],
            "candidates": [
                {
                    "lane": c.lane,
                    "intent": c.intent,
                    "source": c.source,
                    "confidence": round(c.confidence, 3),
                    "reason": c.reason,
                    "tool_name": c.tool_name,
                }
                for c in self.candidates
            ],
            "selected": {
                "lane": self.selected.lane,
                "intent": self.selected.intent,
                "source": self.selected.source,
                "confidence": round(self.selected.confidence, 3),
            }
            if self.selected
            else None,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


@dataclass(frozen=True)
class ToolRouteResult:
    """Result of tool-first routing check."""

    matched: bool
    lane: str = "realtime"
    reason: str = ""
    tool_name: str | None = None
    confidence: float = 0.0
    latency_class: str = "moderate"


# ── Keyword → Tool mapping ──────────────────────────────────────────

# Maps query keywords to tool names. Used for fast tool-first matching
# without needing the LLM.
KEYWORD_TOOL_MAP: dict[frozenset[str], tuple[str, str, float]] = {
    # (keywords) → (tool_name, intent, confidence)
    frozenset({"time", "clock", "hour"}): ("local_now", "time_query", 0.95),
    frozenset({"day", "weekday", "today"}): ("local_now", "day_query", 0.90),
    frozenset({"date", "month", "year"}): ("local_now", "date_query", 0.90),
    frozenset({"calculate", "math", "plus", "minus", "times", "divided"}): (
        "calculator",
        "math_query",
        0.90,
    ),
    frozenset({"multiply", "add", "subtract", "divide", "sum"}): (
        "calculator",
        "math_query",
        0.85,
    ),
}

# Domain keyword → tool domain mapping for ToolPolicy lookup
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "utility": ["time", "clock", "calculate", "math", "date", "day"],
    "file": [
        "file",
        "read",
        "write",
        "save",
        "create",
        "delete",
        "folder",
        "directory",
    ],
    "web": ["website", "url", "fetch", "scrape", "browse", "search", "page", "link"],
    "vision": ["screen", "screenshot", "capture", "see", "look", "display", "ocr"],
    "code": ["code", "python", "script", "function", "debug", "compile", "run"],
    "memory": ["memory", "remember", "recall", "forget", "memories"],
    "system": ["app", "launch", "open", "focus", "switch", "status", "process"],
}


class ToolRouter:
    """Tool-first router that checks if registered tools can handle a query.

    Consults ToolPolicy metadata to determine:
    - Which tool domain matches the query
    - Whether the tool should run in realtime or BG1
    - Expected latency class
    - Voice-friendly result policy

    This enables tool-first routing: tools answer before the LLM guesses.
    """

    def __init__(self, tool_policy: ToolPolicy | None = None) -> None:
        self._tool_policy = tool_policy or ToolPolicy()
        self._classifier = TaskClassifier()
        self._admission = AdmissionControl(max_active_jobs=1, max_queue_length=1)

    @property
    def tool_policy(self) -> ToolPolicy:
        return self._tool_policy

    def check_tool_first(
        self,
        normalized_text: str,
        tokens: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ToolRouteResult:
        """Check if a registered tool can handle this query directly.

        Args:
            normalized_text: Normalized user input
            tokens: Pre-tokenized input (optional)
            context: Optional routing context (system load, etc.)

        Returns:
            ToolRouteResult with match details
        """
        if tokens is None:
            tokens = normalized_text.lower().split()
        token_set = frozenset(tokens)

        # 1. Check keyword → tool map (fastest path)
        for keywords, (tool_name, intent, confidence) in KEYWORD_TOOL_MAP.items():
            if keywords & token_set:
                meta = self._tool_policy.get_metadata(tool_name)
                if meta is not None:
                    use_realtime = self._tool_policy.should_use_realtime(
                        tool_name, context
                    )
                    return ToolRouteResult(
                        matched=True,
                        lane="realtime" if use_realtime else "bg1",
                        reason=f"tool_first_{intent}",
                        tool_name=tool_name,
                        confidence=confidence,
                        latency_class=meta.latency_class.value
                        if hasattr(meta.latency_class, "value")
                        else str(meta.latency_class)
                        if meta
                        else "moderate",
                    )

        # 2. Check domain keywords → domain tools
        matched_domain = self._match_domain(token_set)
        if matched_domain:
            domain_tools = self._tool_policy.get_tools_by_domain(matched_domain)
            if domain_tools:
                best_tool = domain_tools[0]  # First match in domain
                use_realtime = self._tool_policy.should_use_realtime(
                    best_tool.tool_name, context
                )
                return ToolRouteResult(
                    matched=True,
                    lane="realtime" if use_realtime else "bg1",
                    reason=f"tool_domain_{matched_domain}",
                    tool_name=best_tool.tool_name,
                    confidence=0.7,
                    latency_class=best_tool.latency_class.value
                    if hasattr(best_tool.latency_class, "value")
                    else str(best_tool.latency_class),
                )

        # 3. No tool match
        return ToolRouteResult(matched=False)

    def get_tool_voice_summary(
        self,
        tool_name: str,
        result: Any,
        elapsed_ms: float,
    ) -> str:
        """Get voice-friendly summary for a tool result.

        Args:
            tool_name: Tool that produced the result
            result: Tool execution result
            elapsed_ms: Execution time

        Returns:
            Voice-friendly summary string
        """
        return self._tool_policy.get_voice_summary(tool_name, result, elapsed_ms)

    def route_with_trace(
        self,
        normalized_text: str,
        tokens: list[str] | None = None,
        context: dict[str, Any] | None = None,
        existing_candidates: list[RouteCandidate] | None = None,
    ) -> RouteTrace:
        """Route with full candidate trace for observability.

        Produces a RouteTrace with all considered candidates,
        useful for debugging and route analysis.

        Args:
            normalized_text: Normalized user input
            tokens: Pre-tokenized input
            context: Optional routing context
            existing_candidates: Pre-existing candidates from earlier layers

        Returns:
            RouteTrace with all candidates and selected best
        """
        trace = RouteTrace(query=normalized_text)

        # Add any existing candidates from earlier routing layers
        if existing_candidates:
            for c in existing_candidates:
                trace.add(c)

        # Add tool-first candidate
        tool_result = self.check_tool_first(normalized_text, tokens, context)
        if tool_result.matched:
            trace.add(
                RouteCandidate(
                    lane=tool_result.lane,
                    intent=tool_result.reason,
                    source="tool_first",
                    confidence=tool_result.confidence,
                    reason=tool_result.reason,
                    tool_name=tool_result.tool_name,
                    latency_class=tool_result.latency_class,
                )
            )

        # Add classifier fallback candidate
        classifier = self._classifier.classify(normalized_text)
        trace.add(
            RouteCandidate(
                lane=classifier.lane,
                intent="general_chat"
                if classifier.lane == "realtime"
                else "heavy_task",
                source="classifier",
                confidence=0.3,  # Low confidence fallback
                reason=classifier.reason,
            )
        )

        # Select best
        trace.select_best()
        return trace

    def _match_domain(self, token_set: frozenset[str]) -> str | None:
        """Match tokens to a tool domain."""
        best_domain: str | None = None
        best_overlap = 0

        for domain, keywords in DOMAIN_KEYWORDS.items():
            overlap = len(token_set & frozenset(keywords))
            if overlap > best_overlap:
                best_overlap = overlap
                best_domain = domain

        return best_domain if best_overlap >= 1 else None

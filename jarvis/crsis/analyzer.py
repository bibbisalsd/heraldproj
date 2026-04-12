"""DecisionLogAnalyzer - Analyze event logs for patterns."""

from __future__ import annotations


from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jarvis.crsis.contracts import PatternFinding


@dataclass(frozen=True)
class AnalysisWindow:
    """Time window for analysis."""

    start: str
    end: str
    hours: int


class DecisionLogAnalyzer:
    """Analyze event logs to detect systematic issues.

    Detects:
    - Misrouting: Intents systematically routed to wrong handlers
    - Empty tool results: Tools returning no useful data
    - Correction clusters: Repeated corrections in short time windows
    """

    def __init__(self, event_log_accessor: Any | None = None) -> None:
        """Initialize analyzer.

        Args:
            event_log_accessor: Object with read_log() method for event access
        """
        self._event_log = event_log_accessor

    def analyze_last_n_hours(
        self, hours: int = 24, event_log: Any | None = None
    ) -> list[PatternFinding]:
        """Analyze events from the last N hours."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)

        log = event_log or self._event_log
        if log is None:
            return []

        # read_log doesn't support 'after' filter, so read today's events and filter
        events = log.read_log()
        # Filter events by timestamp
        filtered_events = []
        for event in events:
            event_ts = event.get("timestamp", "")
            if event_ts and event_ts >= start.isoformat():
                filtered_events.append(event)

        return self._analyze_events(
            filtered_events, AnalysisWindow(start.isoformat(), now.isoformat(), hours)
        )

    def _analyze_events(
        self, events: list[dict], window: AnalysisWindow
    ) -> list[PatternFinding]:
        """Analyze events and return pattern findings."""
        findings: list[PatternFinding] = []

        # Group events by type for analysis
        events_by_type: dict[str, list[dict]] = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event)

        # Run detectors
        findings.extend(self._detect_misrouting(events_by_type, window))
        findings.extend(self._detect_empty_tool_results(events_by_type, window))
        findings.extend(self._detect_correction_clusters(events_by_type, window))
        findings.extend(self._detect_latency_bottlenecks(events_by_type, window))

        return findings

    def _detect_latency_bottlenecks(
        self, events_by_type: dict[str, list[dict]], window: AnalysisWindow
    ) -> list[PatternFinding]:
        """Detect tools that are consistently slow in the realtime lane."""
        findings = []
        turn_events = events_by_type.get("turn_complete", [])
        if not turn_events:
            return findings

        # tool_name -> [latency_ms]
        realtime_latencies: dict[str, list[float]] = {}

        for event in turn_events:
            artifact = event.get("turn_artifact")
            if not artifact or artifact.get("chosen_route") != "realtime":
                continue

            # If a tool was used in realtime, check its latency
            # New TurnArtifact has tool_summaries and latency_breakdown
            tools = artifact.get("tools_used", [])
            breakdown = artifact.get("latency_breakdown", {})

            # Simple heuristic: if tool_exec_ms exists and > 1500ms
            tool_ms = breakdown.get("tool_exec_ms", 0)
            if tool_ms > 1500 and tools:
                tool_name = tools[0]  # Assume primary tool
                if tool_name not in realtime_latencies:
                    realtime_latencies[tool_name] = []
                realtime_latencies[tool_name].append(tool_ms)

        for tool_name, latencies in realtime_latencies.items():
            if len(latencies) >= 3:
                avg = sum(latencies) / len(latencies)
                findings.append(
                    PatternFinding(
                        pattern_type="latency_bottleneck",
                        affected_component=f"tools:{tool_name}",
                        evidence_count=len(latencies),
                        confidence=0.9,
                        examples=[
                            f"Tool '{tool_name}' averaged {avg:.0f}ms in realtime lane ({len(latencies)} times)"
                        ],
                        time_range=(window.start, window.end),
                    )
                )

        return findings

    def _detect_misrouting(
        self, events_by_type: dict[str, list[dict]], window: AnalysisWindow
    ) -> list[PatternFinding]:
        """Detect systematically misrouted intents."""
        findings = []

        # Look for intent_dispatch events followed by correction signals
        dispatch_events = events_by_type.get("intent_dispatch", [])
        correction_events = events_by_type.get("satisfaction_signal", [])

        if not dispatch_events or not correction_events:
            return findings

        # Group corrections by intent
        corrections_by_intent: dict[str, int] = {}
        dispatches_by_intent: dict[str, int] = {}

        for event in dispatch_events:
            intent = event.get("payload", {}).get("intent", "unknown")
            dispatches_by_intent[intent] = dispatches_by_intent.get(intent, 0) + 1

        for event in correction_events:
            payload = event.get("payload", {})
            if payload.get("signal_type") == "correction":
                intent = payload.get("intent", "unknown")
                corrections_by_intent[intent] = corrections_by_intent.get(intent, 0) + 1

        # Find intents with high correction rates
        for intent, corrections in corrections_by_intent.items():
            dispatches = dispatches_by_intent.get(intent, 1)
            correction_rate = corrections / dispatches

            if correction_rate > 0.3 and corrections >= 3:  # >30% correction rate
                findings.append(
                    PatternFinding(
                        pattern_type="misrouting",
                        affected_component=f"prompt_dispatcher:{intent}",
                        evidence_count=corrections,
                        confidence=min(0.95, correction_rate + 0.2),
                        examples=[f"Intent '{intent}' corrected {corrections} times"],
                        time_range=(window.start, window.end),
                    )
                )

        return findings

    def _detect_empty_tool_results(
        self, events_by_type: dict[str, list[dict]], window: AnalysisWindow
    ) -> list[PatternFinding]:
        """Detect tools returning empty or failed results."""
        findings = []

        tool_events = events_by_type.get("tool_call", [])
        if not tool_events:
            return findings

        # Group by tool name
        empty_results_by_tool: dict[str, int] = {}
        calls_by_tool: dict[str, int] = {}

        for event in tool_events:
            tool_name = event.get("payload", {}).get("tool_name", "unknown")
            calls_by_tool[tool_name] = calls_by_tool.get(tool_name, 0) + 1

            result = event.get("payload", {}).get("result")
            if (
                result is None
                or result == ""
                or (isinstance(result, dict) and not result)
            ):
                empty_results_by_tool[tool_name] = (
                    empty_results_by_tool.get(tool_name, 0) + 1
                )

        # Find tools with high empty result rates
        for tool_name, empty_count in empty_results_by_tool.items():
            total = calls_by_tool.get(tool_name, 1)
            empty_rate = empty_count / total

            if empty_rate > 0.5 and empty_count >= 3:  # >50% empty results
                findings.append(
                    PatternFinding(
                        pattern_type="empty_tool",
                        affected_component=f"tools:{tool_name}",
                        evidence_count=empty_count,
                        confidence=min(0.95, empty_rate + 0.2),
                        examples=[
                            f"Tool '{tool_name}' returned empty {empty_count} times"
                        ],
                        time_range=(window.start, window.end),
                    )
                )

        return findings

    def _detect_correction_clusters(
        self, events_by_type: dict[str, list[dict]], window: AnalysisWindow
    ) -> list[PatternFinding]:
        """Detect clusters of corrections in short time windows."""
        findings = []

        correction_events = events_by_type.get("satisfaction_signal", [])
        if not correction_events:
            return findings

        # Sort by timestamp
        sorted_corrections = sorted(
            correction_events,
            key=lambda e: e.get("timestamp", ""),
        )

        # Find clusters (3+ corrections within 5 minutes)
        cluster_window = timedelta(minutes=5)
        clusters: list[list[dict]] = []
        current_cluster: list[dict] = []

        for event in sorted_corrections:
            event_time = datetime.fromisoformat(event.get("timestamp", ""))
            if not current_cluster:
                current_cluster.append(event)
            else:
                first_time = datetime.fromisoformat(
                    current_cluster[0].get("timestamp", "")
                )
                if event_time - first_time <= cluster_window:
                    current_cluster.append(event)
                else:
                    if len(current_cluster) >= 3:
                        clusters.append(current_cluster)
                    current_cluster = [event]

        if len(current_cluster) >= 3:
            clusters.append(current_cluster)

        # Create findings for clusters
        for cluster in clusters:
            intents = set()
            for event in cluster:
                intent = event.get("payload", {}).get("intent", "unknown")
                intents.add(intent)

            findings.append(
                PatternFinding(
                    pattern_type="correction_cluster",
                    affected_component=f"conversation:{','.join(intents)}",
                    evidence_count=len(cluster),
                    confidence=0.8,
                    examples=[f"{len(cluster)} corrections in 5 minutes"],
                    time_range=(window.start, window.end),
                )
            )

        return findings

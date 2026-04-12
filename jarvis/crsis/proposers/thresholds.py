"""ThresholdProposer - Propose threshold adjustments."""

from __future__ import annotations


from typing import Any


class ThresholdProposer:
    """Propose threshold adjustments for CRSIS and routing.

    Analyzes patterns and suggests threshold changes to reduce
    false positives/negatives in detection and routing.
    """

    # Default thresholds
    DEFAULT_THRESHOLDS = {
        "routing_confidence_threshold": 0.7,
        "tool_empty_rate_threshold": 0.5,
        "tool_failure_rate_threshold": 0.3,
        "correction_cluster_window_minutes": 5,
        "correction_cluster_min_count": 3,
    }

    def __init__(self) -> None:
        self._current_thresholds = dict(self.DEFAULT_THRESHOLDS)

    def propose(self, pattern: Any) -> dict[str, Any] | None:
        """Generate a threshold proposal from a pattern.

        Args:
            pattern: PatternFinding with detection data

        Returns:
            Proposal dict or None if no proposal generated
        """
        if pattern.pattern_type == "empty_tool":
            return self._propose_tool_threshold(pattern)
        elif pattern.pattern_type == "misrouting":
            return self._propose_routing_threshold(pattern)
        elif pattern.pattern_type == "correction_cluster":
            return self._propose_cluster_threshold(pattern)
        return None

    def _propose_tool_threshold(self, pattern: Any) -> dict[str, Any] | None:
        """Propose tool-related threshold adjustment."""
        # Extract tool name from affected_component
        component = pattern.affected_component
        if ":" in component:
            _, tool_name = component.split(":", 1)
        else:
            tool_name = "unknown"

        # If empty rate is very high, suggest lowering threshold for flagging
        if pattern.confidence > 0.8:
            current = self._current_thresholds["tool_empty_rate_threshold"]
            proposed = max(0.3, current - 0.1)  # Lower by 0.1, min 0.3

            return {
                "target_file": "jarvis/crsis/defaults.py",
                "target_structure": "TOOL_EMPTY_RATE_THRESHOLD",
                "proposed_change": {
                    "tool": tool_name,
                    "current": current,
                    "proposed": proposed,
                },
                "expected_impact": f"Flag '{tool_name}' issues earlier (threshold {current} → {proposed})",
                "rollback_path": f"Restore TOOL_EMPTY_RATE_THRESHOLD to {current}",
            }

        return None

    def _propose_routing_threshold(self, pattern: Any) -> dict[str, Any] | None:
        """Propose routing threshold adjustment."""
        if pattern.confidence > 0.7:
            current = self._current_thresholds["routing_confidence_threshold"]
            proposed = min(0.9, current + 0.05)  # Raise by 0.05, max 0.9

            return {
                "target_file": "jarvis/brain_core/task_classifier.py",
                "target_structure": "ROUTING_CONFIDENCE_THRESHOLD",
                "proposed_change": {
                    "current": current,
                    "proposed": proposed,
                },
                "expected_impact": f"Reduce misrouting by requiring higher confidence ({current} → {proposed})",
                "rollback_path": f"Restore ROUTING_CONFIDENCE_THRESHOLD to {current}",
            }

        return None

    def _propose_cluster_threshold(self, pattern: Any) -> dict[str, Any] | None:
        """Propose correction cluster threshold adjustment."""
        # If clusters are detected frequently, might need to adjust window or count
        return {
            "target_file": "jarvis/crsis/defaults.py",
            "target_structure": "CORRECTION_CLUSTER_MIN_COUNT",
            "proposed_change": {
                "current": self._current_thresholds["correction_cluster_min_count"],
                "proposed": 2,  # Lower to catch clusters earlier
            },
            "expected_impact": "Detect correction clusters earlier (3 → 2 corrections)",
            "rollback_path": "Restore CORRECTION_CLUSTER_MIN_COUNT to 3",
        }

    def update_threshold(self, name: str, value: float) -> None:
        """Update a threshold value."""
        if name in self._current_thresholds:
            self._current_thresholds[name] = value

    def get_current(self, name: str) -> float | None:
        """Get current threshold value."""
        return self._current_thresholds.get(name)

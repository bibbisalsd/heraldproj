"""ToolResultAnalyzer - Detect empty or failed tool results."""

from __future__ import annotations


from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResultFinding:
    """Finding for tool result issues."""

    tool_name: str
    empty_count: int
    total_calls: int
    empty_rate: float
    failure_count: int
    failure_rate: float


class ToolResultAnalyzer:
    """Analyze tool results for quality issues.

    Detects:
    - Empty results: Tools returning None, "", or empty dicts
    - Failures: Tools raising exceptions
    """

    def __init__(self) -> None:
        self._call_counts: dict[str, int] = {}
        self._empty_counts: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}

    def record_call(self, tool_name: str, result: Any, success: bool = True) -> None:
        """Record a tool call result."""
        self._call_counts[tool_name] = self._call_counts.get(tool_name, 0) + 1

        if not success:
            self._failure_counts[tool_name] = self._failure_counts.get(tool_name, 0) + 1
        elif self._is_empty(result):
            self._empty_counts[tool_name] = self._empty_counts.get(tool_name, 0) + 1

    def _is_empty(self, result: Any) -> bool:
        """Check if result is empty."""
        if result is None:
            return True
        if result == "":
            return True
        if isinstance(result, dict) and not result:
            return True
        if isinstance(result, list) and not result:
            return True
        return False

    def detect(
        self,
        min_calls: int = 5,
        min_empty_rate: float = 0.5,
        min_failure_rate: float = 0.3,
    ) -> list[ToolResultFinding]:
        """Detect tools with quality issues.

        Args:
            min_calls: Minimum calls to flag
            min_empty_rate: Minimum empty rate to flag
            min_failure_rate: Minimum failure rate to flag

        Returns: list of ToolResultFinding for flagged tools
        """
        findings = []

        for tool_name in self._call_counts:
            total = self._call_counts[tool_name]
            if total < min_calls:
                continue

            empty = self._empty_counts.get(tool_name, 0)
            failures = self._failure_counts.get(tool_name, 0)

            empty_rate = empty / total
            failure_rate = failures / total

            if empty_rate >= min_empty_rate or failure_rate >= min_failure_rate:
                findings.append(
                    ToolResultFinding(
                        tool_name=tool_name,
                        empty_count=empty,
                        total_calls=total,
                        empty_rate=round(empty_rate, 3),
                        failure_count=failures,
                        failure_rate=round(failure_rate, 3),
                    )
                )

        return findings

    def get_statistics(self) -> dict[str, Any]:
        """Get tool result statistics."""
        total_calls = sum(self._call_counts.values())
        total_empty = sum(self._empty_counts.values())
        total_failures = sum(self._failure_counts.values())

        return {
            "total_calls": total_calls,
            "total_empty": total_empty,
            "total_failures": total_failures,
            "overall_empty_rate": round(total_empty / total_calls, 3)
            if total_calls > 0
            else 0.0,
            "overall_failure_rate": round(total_failures / total_calls, 3)
            if total_calls > 0
            else 0.0,
            "tools_tracked": len(self._call_counts),
        }

    def reset(self) -> None:
        """Reset all counters."""
        self._call_counts.clear()
        self._empty_counts.clear()
        self._failure_counts.clear()

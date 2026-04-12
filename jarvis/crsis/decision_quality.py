"""DecisionQuality - Log routing confidence and tool result quality."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DecisionQualityRecord:
    """Record of decision quality for a turn."""

    turn_id: str
    routing_confidence: float
    tool_result_quality: float  # 0.0-1.0
    outcome: str  # "success", "partial", "failure"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DecisionQualityLogger:
    """Log and analyze decision quality metrics."""

    def __init__(self) -> None:
        self._records: list[DecisionQualityRecord] = []
        self._max_history = 1000

    def log(
        self,
        turn_id: str,
        routing_confidence: float,
        tool_result_quality: float,
        outcome: str,
        metadata: dict[str, Any] | None = None,
    ) -> DecisionQualityRecord:
        """Log a decision quality record."""
        record = DecisionQualityRecord(
            turn_id=turn_id,
            routing_confidence=routing_confidence,
            tool_result_quality=tool_result_quality,
            outcome=outcome,
            metadata=metadata or {},
        )
        self._records.append(record)

        # Trim history
        if len(self._records) > self._max_history:
            self._records = self._records[-self._max_history :]

        return record

    def get_records(
        self,
        turn_id: str | None = None,
        outcome: str | None = None,
        min_routing_confidence: float | None = None,
        limit: int = 100,
    ) -> list[DecisionQualityRecord]:
        """Query decision quality records."""
        results = []
        for record in self._records:
            if turn_id and record.turn_id != turn_id:
                continue
            if outcome and record.outcome != outcome:
                continue
            if (
                min_routing_confidence
                and record.routing_confidence < min_routing_confidence
            ):
                continue
            results.append(record)
        return results[-limit:]  # Most recent

    def get_statistics(self, last_n: int = 100) -> dict[str, Any]:
        """Get decision quality statistics."""
        records = self._records[-last_n:]
        if not records:
            return {
                "count": 0,
                "avg_routing_confidence": 0.0,
                "avg_tool_result_quality": 0.0,
                "success_rate": 0.0,
            }

        avg_routing = sum(r.routing_confidence for r in records) / len(records)
        avg_tool = sum(r.tool_result_quality for r in records) / len(records)
        success_count = sum(1 for r in records if r.outcome == "success")

        return {
            "count": len(records),
            "avg_routing_confidence": round(avg_routing, 3),
            "avg_tool_result_quality": round(avg_tool, 3),
            "success_rate": round(success_count / len(records), 3),
        }

    def get_failure_records(self, last_n: int = 50) -> list[DecisionQualityRecord]:
        """Get records with failure outcomes."""
        records = self._records[-last_n * 2 :]  # Look at more to find failures
        return [r for r in records if r.outcome == "failure"][:last_n]

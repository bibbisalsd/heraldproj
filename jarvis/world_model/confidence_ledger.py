"""ConfidenceLedger - Track turn confidence and aggregate confidence."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TurnConfidence:
    """Confidence score for a single turn."""

    turn_id: str
    confidence: float  # 0.0 to 1.0
    factors: dict[str, float] = field(
        default_factory=dict
    )  # Breakdown of confidence factors
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def with_factor(self, factor_name: str, factor_value: float) -> "TurnConfidence":
        """Create a new TurnConfidence with an added factor."""
        if not 0.0 <= factor_value <= 1.0:
            raise ValueError(
                f"Factor value must be between 0.0 and 1.0, got {factor_value}"
            )
        new_factors = dict(self.factors)
        new_factors[factor_name] = factor_value
        # Recalculate overall confidence as average of factors
        new_confidence = (
            sum(new_factors.values()) / len(new_factors)
            if new_factors
            else self.confidence
        )
        return TurnConfidence(
            turn_id=self.turn_id,
            confidence=new_confidence,
            factors=new_factors,
            timestamp=self.timestamp,
        )


@dataclass(frozen=True)
class ConfidenceLedger:
    """Track aggregate confidence across turns."""

    recent_confidences: list[TurnConfidence] = field(default_factory=list)
    aggregate_confidence: float = 1.0
    failure_log: list[dict[str, Any]] = field(default_factory=list)
    max_history: int = 50

    def add_turn(self, turn_confidence: TurnConfidence) -> "ConfidenceLedger":
        """Add a turn confidence and recalculate aggregate."""
        new_recent = list(self.recent_confidences)
        new_recent.append(turn_confidence)

        # Keep only last N turns
        if len(new_recent) > self.max_history:
            new_recent = new_recent[-self.max_history :]

        # Calculate aggregate as weighted average (recent turns weighted higher)
        if new_recent:
            weights = [i + 1 for i in range(len(new_recent))]
            weighted_sum = sum(tc.confidence * w for tc, w in zip(new_recent, weights))
            total_weight = sum(weights)
            new_aggregate = weighted_sum / total_weight
        else:
            new_aggregate = 1.0

        return ConfidenceLedger(
            recent_confidences=new_recent,
            aggregate_confidence=new_aggregate,
            failure_log=self.failure_log,
            max_history=self.max_history,
        )

    def log_failure(self, failure: dict[str, Any]) -> "ConfidenceLedger":
        """Log a failure event."""
        new_failures = list(self.failure_log)
        new_failures.append(
            {
                **failure,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        # Keep only last 100 failures
        if len(new_failures) > 100:
            new_failures = new_failures[-100:]
        return ConfidenceLedger(
            recent_confidences=self.recent_confidences,
            aggregate_confidence=self.aggregate_confidence,
            failure_log=new_failures,
            max_history=self.max_history,
        )

    def get_recent_average(self, n: int = 10) -> float:
        """Get average confidence of last N turns."""
        recent = self.recent_confidences[-n:]
        if not recent:
            return 1.0
        return sum(tc.confidence for tc in recent) / len(recent)

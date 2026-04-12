"""ModelHealth - Track model availability, latency, and error rates."""

from __future__ import annotations


from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ModelHealth:
    """Model health tracking availability, latency, and error rates."""

    model_name: str
    available: bool = True
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0  # 0.0 to 1.0
    total_calls: int = 0
    error_count: int = 0
    last_used: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None

    def record_call(
        self, latency_ms: float, success: bool, error: str | None = None
    ) -> "ModelHealth":
        """Record a model call and return updated ModelHealth."""
        now = datetime.now(timezone.utc).isoformat()
        new_total = self.total_calls + 1
        new_error_count = self.error_count + (0 if success else 1)
        new_error_rate = new_error_count / new_total if new_total > 0 else 0.0

        # Exponential moving average for latency (alpha=0.3)
        if self.avg_latency_ms == 0.0:
            new_avg_latency = latency_ms
        else:
            new_avg_latency = 0.3 * latency_ms + 0.7 * self.avg_latency_ms

        return ModelHealth(
            model_name=self.model_name,
            available=self.available
            and (new_error_rate < 0.5),  # Auto-disable if >50% errors
            avg_latency_ms=new_avg_latency,
            error_rate=new_error_rate,
            total_calls=new_total,
            error_count=new_error_count,
            last_used=now,
            last_error=error if not success else self.last_error,
            last_error_at=now if not success else self.last_error_at,
        )

    def mark_available(self, available: bool) -> "ModelHealth":
        """Mark model as available or unavailable."""
        return ModelHealth(
            model_name=self.model_name,
            available=available,
            avg_latency_ms=self.avg_latency_ms,
            error_rate=self.error_rate,
            total_calls=self.total_calls,
            error_count=self.error_count,
            last_used=self.last_used,
            last_error=self.last_error,
            last_error_at=self.last_error_at,
        )

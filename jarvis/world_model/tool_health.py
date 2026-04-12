"""ToolHealth - Track tool availability, error rates, and usage."""

from __future__ import annotations


from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ToolHealth:
    """Tool health tracking availability, error rates, and last usage."""

    tool_name: str
    available: bool = True
    error_rate: float = 0.0  # 0.0 to 1.0
    last_used: str | None = None
    total_calls: int = 0
    error_count: int = 0
    last_error: str | None = None
    last_error_at: str | None = None

    def record_call(self, success: bool, error: str | None = None) -> "ToolHealth":
        """Record a tool call and return updated ToolHealth."""
        now = datetime.now(timezone.utc).isoformat()
        new_total = self.total_calls + 1
        new_error_count = self.error_count + (0 if success else 1)
        new_error_rate = new_error_count / new_total if new_total > 0 else 0.0

        return ToolHealth(
            tool_name=self.tool_name,
            available=self.available
            and (new_error_rate < 0.5),  # Auto-disable if >50% errors
            error_rate=new_error_rate,
            last_used=now,
            total_calls=new_total,
            error_count=new_error_count,
            last_error=error if not success else self.last_error,
            last_error_at=now if not success else self.last_error_at,
        )

    def mark_available(self, available: bool) -> "ToolHealth":
        """Mark tool as available or unavailable."""
        return ToolHealth(
            tool_name=self.tool_name,
            available=available,
            error_rate=self.error_rate,
            last_used=self.last_used,
            total_calls=self.total_calls,
            error_count=self.error_count,
            last_error=self.last_error,
            last_error_at=self.last_error_at,
        )

    def reset_stats(self) -> "ToolHealth":
        """Reset error statistics."""
        return ToolHealth(
            tool_name=self.tool_name,
            available=True,
            error_rate=0.0,
            last_used=self.last_used,
            total_calls=0,
            error_count=0,
            last_error=None,
            last_error_at=None,
        )

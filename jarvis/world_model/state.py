"""WorldState - Unified system state snapshot."""

from __future__ import annotations


from dataclasses import dataclass, field
from typing import Any

from jarvis.world_model.user_profile import UserProfile
from jarvis.world_model.task import Task, JobStatus
from jarvis.world_model.tool_health import ToolHealth
from jarvis.world_model.model_health import ModelHealth
from jarvis.world_model.device_status import DeviceStatus
from jarvis.world_model.confidence_ledger import TurnConfidence


@dataclass(frozen=True)
class WorldState:
    """Unified system state snapshot.

    Tracks user profile, task stack, tool availability, model availability,
    device status, and confidence ledger.
    """

    timestamp: str
    user_profile: UserProfile
    task_stack: tuple[Task, ...] = field(default_factory=tuple)
    open_bg1_jobs: tuple[JobStatus, ...] = field(default_factory=tuple)
    tool_availability: dict[str, ToolHealth] = field(default_factory=dict)
    model_availability: dict[str, ModelHealth] = field(default_factory=dict)
    device_status: DeviceStatus | None = None
    recent_turn_confidences: tuple[TurnConfidence, ...] = field(default_factory=tuple)
    aggregate_confidence: float = 1.0
    failure_log: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def with_updates(self, **updates: Any) -> "WorldState":
        """Create a new WorldState with specified fields updated."""
        return WorldState(
            timestamp=self.timestamp,
            user_profile=updates.get("user_profile", self.user_profile),
            task_stack=tuple(updates.get("task_stack", self.task_stack)),
            open_bg1_jobs=tuple(updates.get("open_bg1_jobs", self.open_bg1_jobs)),
            tool_availability=dict(
                updates.get("tool_availability", self.tool_availability)
            ),
            model_availability=dict(
                updates.get("model_availability", self.model_availability)
            ),
            device_status=updates.get("device_status", self.device_status),
            recent_turn_confidences=tuple(
                updates.get("recent_turn_confidences", self.recent_turn_confidences)
            ),
            aggregate_confidence=updates.get(
                "aggregate_confidence", self.aggregate_confidence
            ),
            failure_log=tuple(updates.get("failure_log", self.failure_log)),
        )

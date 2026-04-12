"""StateBuilder - Deterministic event → state transition engine."""

from __future__ import annotations


from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from jarvis.world_model.state import WorldState
from jarvis.world_model.task import Task, JobStatus
from jarvis.world_model.tool_health import ToolHealth
from jarvis.world_model.model_health import ModelHealth
from jarvis.world_model.device_status import DeviceStatus
from jarvis.world_model.confidence_ledger import TurnConfidence


@dataclass(frozen=True)
class EventRecord:
    """An event record for event sourcing."""

    event_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: str
    turn_id: str | None = None


@dataclass(frozen=True)
class StateDiff:
    """Structured diff between two WorldStates."""

    field_name: str
    old_value: Any
    new_value: Any
    change_type: str  # "added", "removed", "modified"


class Event(Protocol):
    """Protocol for event types."""

    event_type: str
    payload: dict[str, Any]


class StateBuilder:
    """Deterministic event → state transition engine.

    Stores events and reconstructs state on demand.
    Applies events immutably - never mutates state.
    """

    def __init__(self) -> None:
        self._events: list[EventRecord] = []
        self._initial_state: WorldState | None = None

    def store_event(self, event: EventRecord) -> None:
        """Store an event for later replay."""
        self._events.append(event)

    def get_events(self, turn_id: str | None = None) -> list[EventRecord]:
        """Get events, optionally filtered by turn_id."""
        if turn_id is None:
            return list(self._events)
        return [e for e in self._events if e.turn_id == turn_id]

    def apply_event(self, state: WorldState, event: EventRecord) -> WorldState:
        """Apply an event to a state and return NEW state (immutable)."""
        handler = getattr(self, f"_handle_{event.event_type}", None)
        if handler is None:
            # Unknown event type - return state unchanged
            return state
        return handler(state, event.payload)

    def reconstruct_state(self, initial_state: WorldState) -> WorldState:
        """Reconstruct state by replaying all events from initial state."""
        state = initial_state
        for event in self._events:
            state = self.apply_event(state, event)
        return state

    def diff(self, before: WorldState, after: WorldState) -> list[StateDiff]:
        """Return structured diff between two states."""
        diffs: list[StateDiff] = []

        # Compare simple fields
        simple_fields = ["timestamp", "aggregate_confidence"]
        for field_name in simple_fields:
            old_val = getattr(before, field_name)
            new_val = getattr(after, field_name)
            if old_val != new_val:
                diffs.append(
                    StateDiff(
                        field_name=field_name,
                        old_value=old_val,
                        new_value=new_val,
                        change_type="modified",
                    )
                )

        # Compare lists (check for additions/removals)
        list_fields = [
            "task_stack",
            "open_bg1_jobs",
            "recent_turn_confidences",
            "failure_log",
        ]
        for field_name in list_fields:
            old_list: list = getattr(before, field_name)
            new_list: list = getattr(after, field_name)
            if len(old_list) != len(new_list):
                if len(new_list) > len(old_list):
                    diffs.append(
                        StateDiff(
                            field_name=field_name,
                            old_value=old_list,
                            new_value=new_list,
                            change_type="added",
                        )
                    )
                else:
                    diffs.append(
                        StateDiff(
                            field_name=field_name,
                            old_value=old_list,
                            new_value=new_list,
                            change_type="removed",
                        )
                    )

        return diffs

    # Event handlers

    def _handle_task_created(self, state: WorldState, payload: dict) -> WorldState:
        """Handle task_created event."""
        task = Task(
            task_id=payload["task_id"],
            description=payload["description"],
            priority=payload.get("priority", 0),
            status=payload.get("status", "pending"),
            metadata=payload.get("metadata", {}),
        )
        new_stack = list(state.task_stack) + [task]
        return state.with_updates(task_stack=new_stack)

    def _handle_task_updated(self, state: WorldState, payload: dict) -> WorldState:
        """Handle task_updated event."""
        task_id = payload["task_id"]
        new_stack = []
        for task in state.task_stack:
            if task.task_id == task_id:
                if "status" in payload:
                    task = task.with_status(payload["status"])
                if "priority" in payload:
                    task = task.with_priority(payload["priority"])
            new_stack.append(task)
        return state.with_updates(task_stack=new_stack)

    def _handle_job_created(self, state: WorldState, payload: dict) -> WorldState:
        """Handle job_created event."""
        job = JobStatus(
            job_id=payload["job_id"],
            task_id=payload["task_id"],
            status=payload.get("status", "queued"),
        )
        new_jobs = list(state.open_bg1_jobs) + [job]
        return state.with_updates(open_bg1_jobs=new_jobs)

    def _handle_job_updated(self, state: WorldState, payload: dict) -> WorldState:
        """Handle job_updated event."""
        job_id = payload["job_id"]
        new_jobs = []
        for job in state.open_bg1_jobs:
            if job.job_id == job_id:
                if "status" in payload:
                    job = job.with_status(payload["status"], payload.get("progress"))
                if "result" in payload:
                    job = job.with_result(payload["result"])
                if "error" in payload:
                    job = job.with_error(payload["error"])
            new_jobs.append(job)
        # Remove completed/failed/cancelled jobs from open list
        new_jobs = [j for j in new_jobs if j.status in {"queued", "running"}]
        return state.with_updates(open_bg1_jobs=new_jobs)

    def _handle_tool_call(self, state: WorldState, payload: dict) -> WorldState:
        """Handle tool_call event."""
        tool_name = payload["tool_name"]
        success = payload.get("success", True)
        error = payload.get("error")

        tool_health = state.tool_availability.get(
            tool_name, ToolHealth(tool_name=tool_name)
        )
        tool_health = tool_health.record_call(success=success, error=error)

        new_availability = dict(state.tool_availability)
        new_availability[tool_name] = tool_health
        return state.with_updates(tool_availability=new_availability)

    def _handle_model_call(self, state: WorldState, payload: dict) -> WorldState:
        """Handle model_call event."""
        model_name = payload["model_name"]
        latency_ms = payload.get("latency_ms", 0)
        success = payload.get("success", True)
        error = payload.get("error")

        model_health = state.model_availability.get(
            model_name, ModelHealth(model_name=model_name)
        )
        model_health = model_health.record_call(
            latency_ms=latency_ms, success=success, error=error
        )

        new_availability = dict(state.model_availability)
        new_availability[model_name] = model_health
        return state.with_updates(model_availability=new_availability)

    def _handle_device_status_change(
        self, state: WorldState, payload: dict
    ) -> WorldState:
        """Handle device_status_change event."""
        device_status = state.device_status or DeviceStatus.all_inactive()

        if "mic_active" in payload:
            device_status = device_status.with_mic(payload["mic_active"])
        if "speaker_active" in payload:
            device_status = device_status.with_speaker(payload["speaker_active"])
        if "screen_active" in payload:
            device_status = device_status.with_screen(payload["screen_active"])
        if "network_state" in payload:
            device_status = device_status.with_network(
                payload["network_state"], payload.get("network_latency_ms")
            )

        return state.with_updates(device_status=device_status)

    def _handle_turn_confidence(self, state: WorldState, payload: dict) -> WorldState:
        """Handle turn_confidence event."""
        turn_confidence = TurnConfidence(
            turn_id=payload["turn_id"],
            confidence=payload["confidence"],
            factors=payload.get("factors", {}),
        )

        new_confidences = list(state.recent_turn_confidences) + [turn_confidence]
        # Keep only last 50
        if len(new_confidences) > 50:
            new_confidences = new_confidences[-50:]

        # Recalculate aggregate
        weights = [i + 1 for i in range(len(new_confidences))]
        weighted_sum = sum(tc.confidence * w for tc, w in zip(new_confidences, weights))
        total_weight = sum(weights)
        new_aggregate = weighted_sum / total_weight

        return state.with_updates(
            recent_turn_confidences=new_confidences,
            aggregate_confidence=new_aggregate,
        )

    def _handle_failure(self, state: WorldState, payload: dict) -> WorldState:
        """Handle failure event."""
        new_failures = list(state.failure_log) + [
            {
                **payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
        # Keep only last 100
        if len(new_failures) > 100:
            new_failures = new_failures[-100:]
        return state.with_updates(failure_log=new_failures)

    def _handle_user_preference(self, state: WorldState, payload: dict) -> WorldState:
        """Handle user_preference event."""
        key = payload["key"]
        value = payload["value"]
        new_profile = state.user_profile.with_preference(key, value)
        return state.with_updates(user_profile=new_profile)

    def _handle_user_verification(self, state: WorldState, payload: dict) -> WorldState:
        """Handle user_verification event."""
        status = payload["status"]
        new_profile = state.user_profile.with_verification_status(status)
        return state.with_updates(user_profile=new_profile)

"""Tests for StateBuilder event sourcing and state transitions."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone

from jarvis.world_model.state import WorldState
from jarvis.world_model.user_profile import UserProfile
from jarvis.world_model.state_builder import StateBuilder, EventRecord, StateDiff
from jarvis.world_model.task import Task, JobStatus
from jarvis.world_model.tool_health import ToolHealth
from jarvis.world_model.model_health import ModelHealth
from jarvis.world_model.device_status import DeviceStatus
from jarvis.world_model.confidence_ledger import TurnConfidence


class TestEventRecord:
    """Test EventRecord dataclass."""

    def test_create_event_record(self):
        """Test creating EventRecord."""
        event = EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={"task_id": "task1", "description": "Test task"},
            timestamp="2026-04-05T00:00:00Z",
        )
        assert event.event_id == "event_001"
        assert event.event_type == "task_created"
        assert event.payload["task_id"] == "task1"
        assert event.turn_id is None

    def test_create_event_with_turn_id(self):
        """Test creating EventRecord with turn_id."""
        event = EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={"task_id": "task1"},
            timestamp="2026-04-05T00:00:00Z",
            turn_id="turn_123",
        )
        assert event.turn_id == "turn_123"


class TestStateDiff:
    """Test StateDiff dataclass."""

    def test_create_state_diff(self):
        """Test creating StateDiff."""
        diff = StateDiff(
            field_name="aggregate_confidence",
            old_value=1.0,
            new_value=0.8,
            change_type="modified",
        )
        assert diff.field_name == "aggregate_confidence"
        assert diff.old_value == 1.0
        assert diff.new_value == 0.8
        assert diff.change_type == "modified"


class TestStateBuilder:
    """Test StateBuilder event sourcing."""

    def get_initial_state(self) -> WorldState:
        """Create initial WorldState for tests."""
        return WorldState(
            timestamp="2026-04-05T00:00:00Z",
            user_profile=UserProfile(user_id="test_user"),
        )

    def test_store_event(self):
        """Test storing events."""
        builder = StateBuilder()
        event = EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={"task_id": "task1"},
            timestamp="2026-04-05T00:00:00Z",
        )
        builder.store_event(event)
        events = builder.get_events()
        assert len(events) == 1
        assert events[0].event_id == "event_001"

    def test_get_events_filtered_by_turn_id(self):
        """Test filtering events by turn_id."""
        builder = StateBuilder()
        builder.store_event(EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={},
            timestamp="2026-04-05T00:00:00Z",
            turn_id="turn_1",
        ))
        builder.store_event(EventRecord(
            event_id="event_002",
            event_type="task_created",
            payload={},
            timestamp="2026-04-05T00:00:01Z",
            turn_id="turn_2",
        ))
        events = builder.get_events(turn_id="turn_1")
        assert len(events) == 1
        assert events[0].event_id == "event_001"

    def test_apply_event_returns_new_state(self):
        """Test apply_event returns new state without mutating."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={"task_id": "task1", "description": "Test task"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert len(state.task_stack) == 0  # Original unchanged
        assert len(new_state.task_stack) == 1  # New state has task

    def test_reconstruct_state(self):
        """Test reconstructing state by replaying events."""
        builder = StateBuilder()
        initial = self.get_initial_state()

        builder.store_event(EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={"task_id": "task1", "description": "Task 1"},
            timestamp="2026-04-05T00:00:00Z",
        ))
        builder.store_event(EventRecord(
            event_id="event_002",
            event_type="task_created",
            payload={"task_id": "task2", "description": "Task 2"},
            timestamp="2026-04-05T00:00:01Z",
        ))

        reconstructed = builder.reconstruct_state(initial)
        assert len(reconstructed.task_stack) == 2

    def test_diff_simple_fields(self):
        """Test diff for simple fields."""
        builder = StateBuilder()
        before = self.get_initial_state()
        after = before.with_updates(aggregate_confidence=0.8)
        diffs = builder.diff(before, after)
        assert len(diffs) == 1
        assert diffs[0].field_name == "aggregate_confidence"
        assert diffs[0].old_value == 1.0
        assert diffs[0].new_value == 0.8

    def test_diff_list_additions(self):
        """Test diff detects list additions."""
        builder = StateBuilder()
        before = self.get_initial_state()
        task = Task(task_id="task1", description="Test")
        after = before.with_updates(task_stack=[task])
        diffs = builder.diff(before, after)
        assert len(diffs) == 1
        assert diffs[0].field_name == "task_stack"
        assert diffs[0].change_type == "added"

    def test_handle_task_created(self):
        """Test _handle_task_created event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="task_created",
            payload={"task_id": "task1", "description": "Test task", "priority": 5},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert len(new_state.task_stack) == 1
        assert new_state.task_stack[0].task_id == "task1"
        assert new_state.task_stack[0].priority == 5

    def test_handle_task_updated(self):
        """Test _handle_task_updated event."""
        builder = StateBuilder()
        task = Task(task_id="task1", description="Test", status="pending", priority=5)
        state = self.get_initial_state().with_updates(task_stack=[task])
        event = EventRecord(
            event_id="event_001",
            event_type="task_updated",
            payload={"task_id": "task1", "status": "completed"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert new_state.task_stack[0].status == "completed"

    def test_handle_job_created(self):
        """Test _handle_job_created event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="job_created",
            payload={"job_id": "job1", "task_id": "task1"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert len(new_state.open_bg1_jobs) == 1
        assert new_state.open_bg1_jobs[0].job_id == "job1"

    def test_handle_job_updated_removes_completed(self):
        """Test _handle_job_updated removes completed jobs."""
        builder = StateBuilder()
        job = JobStatus(job_id="job1", task_id="task1", status="running")
        state = self.get_initial_state().with_updates(open_bg1_jobs=[job])
        event = EventRecord(
            event_id="event_001",
            event_type="job_updated",
            payload={"job_id": "job1", "status": "completed"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert len(new_state.open_bg1_jobs) == 0  # Completed job removed

    def test_handle_tool_call(self):
        """Test _handle_tool_call event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="tool_call",
            payload={"tool_name": "calculator", "success": True},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert "calculator" in new_state.tool_availability
        assert new_state.tool_availability["calculator"].total_calls == 1

    def test_handle_tool_call_failure(self):
        """Test _handle_tool_call with failure."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="tool_call",
            payload={"tool_name": "calculator", "success": False, "error": "Error"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert new_state.tool_availability["calculator"].error_rate == 1.0

    def test_handle_model_call(self):
        """Test _handle_model_call event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="model_call",
            payload={"model_name": "llama3.2:1b", "latency_ms": 150, "success": True},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert "llama3.2:1b" in new_state.model_availability
        assert new_state.model_availability["llama3.2:1b"].avg_latency_ms == 150.0

    def test_handle_device_status_change(self):
        """Test _handle_device_status_change event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="device_status_change",
            payload={"mic_active": True},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert new_state.device_status is not None
        assert new_state.device_status.mic_active is True

    def test_handle_turn_confidence(self):
        """Test _handle_turn_confidence event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="turn_confidence",
            payload={"turn_id": "turn_1", "confidence": 0.9},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert len(new_state.recent_turn_confidences) == 1
        assert new_state.recent_turn_confidences[0].confidence == 0.9

    def test_handle_failure(self):
        """Test _handle_failure event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="failure",
            payload={"component": "tool", "error": "Connection error"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert len(new_state.failure_log) == 1
        assert new_state.failure_log[0]["component"] == "tool"

    def test_handle_user_preference(self):
        """Test _handle_user_preference event."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="user_preference",
            payload={"key": "theme", "value": "dark"},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert new_state.user_profile.preferences.get("theme") == "dark"

    def test_unknown_event_type_returns_state_unchanged(self):
        """Test unknown event types return state unchanged."""
        builder = StateBuilder()
        state = self.get_initial_state()
        event = EventRecord(
            event_id="event_001",
            event_type="unknown_event_type",
            payload={},
            timestamp="2026-04-05T00:00:00Z",
        )
        new_state = builder.apply_event(state, event)
        assert new_state is state  # Same object returned

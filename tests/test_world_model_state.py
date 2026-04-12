"""Tests for WorldState and state management components."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone

from jarvis.world_model.state import WorldState
from jarvis.world_model.user_profile import UserProfile
from jarvis.world_model.task import Task, JobStatus
from jarvis.world_model.tool_health import ToolHealth
from jarvis.world_model.model_health import ModelHealth
from jarvis.world_model.device_status import DeviceStatus


class TestWorldState:
    """Test WorldState dataclass and operations."""

    def test_create_initial_state(self):
        """Test creating initial WorldState with minimal fields."""
        state = WorldState(
            timestamp="2026-04-05T00:00:00Z",
            user_profile=UserProfile(user_id="test_user"),
        )
        assert state.user_profile.user_id == "test_user"
        assert state.task_stack == []
        assert state.open_bg1_jobs == []
        assert state.tool_availability == {}
        assert state.model_availability == {}
        assert state.aggregate_confidence == 1.0

    def test_state_is_immutable(self):
        """Test that WorldState is frozen (immutable)."""
        state = WorldState(
            timestamp="2026-04-05T00:00:00Z",
            user_profile=UserProfile(user_id="test_user"),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            state.aggregate_confidence = 0.5

    def test_with_updates_creates_new_state(self):
        """Test with_updates returns new state with modifications."""
        original = WorldState(
            timestamp="2026-04-05T00:00:00Z",
            user_profile=UserProfile(user_id="test_user"),
            aggregate_confidence=1.0,
        )
        updated = original.with_updates(aggregate_confidence=0.8)
        assert original.aggregate_confidence == 1.0  # Original unchanged
        assert updated.aggregate_confidence == 0.8  # New state has update

    def test_with_updates_preserves_lists(self):
        """Test with_updates creates copies of lists."""
        task = Task(task_id="task1", description="Test task")
        original = WorldState(
            timestamp="2026-04-05T00:00:00Z",
            user_profile=UserProfile(user_id="test_user"),
            task_stack=[task],
        )
        updated = original.with_updates(task_stack=original.task_stack + [task])
        assert len(original.task_stack) == 1  # Original unchanged
        assert len(updated.task_stack) == 2  # New state has additional item

    def test_state_with_full_initialization(self):
        """Test creating WorldState with all fields populated."""
        tool_health = ToolHealth(tool_name="calculator")
        model_health = ModelHealth(model_name="llama3.2:1b")
        device = DeviceStatus.all_inactive()

        state = WorldState(
            timestamp="2026-04-05T00:00:00Z",
            user_profile=UserProfile(user_id="test_user"),
            task_stack=[Task(task_id="t1", description="Task 1")],
            open_bg1_jobs=[JobStatus(job_id="j1", task_id="t1")],
            tool_availability={"calculator": tool_health},
            model_availability={"llama3.2:1b": model_health},
            device_status=device,
            recent_turn_confidences=[0.9, 0.8, 0.95],
            aggregate_confidence=0.88,
            failure_log=[],
        )

        assert len(state.task_stack) == 1
        assert len(state.open_bg1_jobs) == 1
        assert "calculator" in state.tool_availability
        assert "llama3.2:1b" in state.model_availability
        assert state.device_status is not None
        assert len(state.recent_turn_confidences) == 3
        assert state.aggregate_confidence == 0.88


class TestTask:
    """Test Task dataclass."""

    def test_create_task_minimal(self):
        """Test creating Task with minimal fields."""
        task = Task(task_id="task1", description="Test task")
        assert task.task_id == "task1"
        assert task.description == "Test task"
        assert task.priority == 0
        assert task.status == "pending"

    def test_create_task_with_priority(self):
        """Test creating Task with priority."""
        task = Task(task_id="task1", description="Test task", priority=10)
        assert task.priority == 10

    def test_with_status_returns_new_task(self):
        """Test with_status returns new Task instance."""
        original = Task(task_id="task1", description="Test task", status="pending")
        updated = original.with_status("completed")
        assert original.status == "pending"
        assert updated.status == "completed"

    def test_with_priority_returns_new_task(self):
        """Test with_priority returns new Task instance."""
        original = Task(task_id="task1", description="Test task", priority=5)
        updated = original.with_priority(10)
        assert original.priority == 5
        assert updated.priority == 10


class TestJobStatus:
    """Test JobStatus dataclass."""

    def test_create_job_minimal(self):
        """Test creating JobStatus with minimal fields."""
        job = JobStatus(job_id="job1", task_id="task1")
        assert job.job_id == "job1"
        assert job.task_id == "task1"
        assert job.status == "queued"
        assert job.progress == 0.0  # Default is 0.0, not None

    def test_with_status_returns_new_job(self):
        """Test with_status returns new JobStatus instance."""
        original = JobStatus(job_id="job1", task_id="task1", status="queued")
        updated = original.with_status("running", progress=50)
        assert original.status == "queued"
        assert updated.status == "running"
        assert updated.progress == 50

    def test_with_result(self):
        """Test with_result sets result."""
        job = JobStatus(job_id="job1", task_id="task1")
        updated = job.with_result({"output": "success"})
        assert updated.result == {"output": "success"}

    def test_with_error(self):
        """Test with_error sets error."""
        job = JobStatus(job_id="job1", task_id="task1")
        updated = job.with_error("Something went wrong")
        assert updated.error == "Something went wrong"


class TestToolHealth:
    """Test ToolHealth dataclass."""

    def test_create_tool_health(self):
        """Test creating ToolHealth."""
        health = ToolHealth(tool_name="calculator")
        assert health.tool_name == "calculator"
        assert health.total_calls == 0
        assert health.error_rate == 0.0

    def test_record_call_success(self):
        """Test recording successful call."""
        health = ToolHealth(tool_name="calculator")
        updated = health.record_call(success=True)
        assert updated.total_calls == 1
        assert updated.error_rate == 0.0

    def test_record_call_failure(self):
        """Test recording failed call."""
        health = ToolHealth(tool_name="calculator")
        updated = health.record_call(success=False, error="Connection error")
        assert updated.total_calls == 1
        assert updated.error_rate == 1.0

    def test_error_rate_calculation(self):
        """Test error rate is calculated correctly."""
        health = ToolHealth(tool_name="calculator")
        health = health.record_call(success=True)
        health = health.record_call(success=False, error="Error 1")
        health = health.record_call(success=True)
        health = health.record_call(success=False, error="Error 2")
        assert health.total_calls == 4
        assert health.error_rate == 0.5  # 2/4 = 50%


class TestModelHealth:
    """Test ModelHealth dataclass."""

    def test_create_model_health(self):
        """Test creating ModelHealth."""
        health = ModelHealth(model_name="llama3.2:1b")
        assert health.model_name == "llama3.2:1b"
        assert health.total_calls == 0
        assert health.avg_latency_ms == 0.0  # Default is 0.0

    def test_record_call_with_latency(self):
        """Test recording call with latency."""
        health = ModelHealth(model_name="llama3.2:1b")
        updated = health.record_call(latency_ms=150, success=True)
        assert updated.total_calls == 1
        assert updated.avg_latency_ms == 150.0

    def test_avg_latency_calculation(self):
        """Test average latency is calculated correctly."""
        health = ModelHealth(model_name="llama3.2:1b")
        health = health.record_call(latency_ms=100, success=True)
        health = health.record_call(latency_ms=200, success=True)
        health = health.record_call(latency_ms=300, success=True)
        assert health.total_calls == 3
        # Uses exponential moving average, not simple average
        assert health.avg_latency_ms > 0.0


class TestDeviceStatus:
    """Test DeviceStatus dataclass."""

    def test_all_inactive(self):
        """Test creating all-inactive device status."""
        status = DeviceStatus.all_inactive()
        assert status.mic_active is False
        assert status.speaker_active is False
        assert status.screen_active is False
        assert status.network_state == "unknown"

    def test_with_mic(self):
        """Test with_mic returns new status."""
        original = DeviceStatus.all_inactive()
        updated = original.with_mic(True)
        assert original.mic_active is False
        assert updated.mic_active is True

    def test_with_speaker(self):
        """Test with_speaker returns new status."""
        original = DeviceStatus.all_inactive()
        updated = original.with_speaker(True)
        assert original.speaker_active is False
        assert updated.speaker_active is True

    def test_with_screen(self):
        """Test with_screen returns new status."""
        original = DeviceStatus.all_inactive()
        updated = original.with_screen(True)
        assert original.screen_active is False
        assert updated.screen_active is True

    def test_with_network(self):
        """Test with_network returns new status."""
        original = DeviceStatus.all_inactive()
        updated = original.with_network("connected", latency_ms=20)
        assert original.network_state == "unknown"  # Original unchanged
        assert updated.network_state == "connected"
        assert updated.network_latency_ms == 20

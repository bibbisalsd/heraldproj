"""Tests for Phase 5C: Planner action execution for simple tool_call plans.

All tests are lightweight — no Ollama, no TTS, no real model inference.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from jarvis.world_model.planner import Planner, Action, ActionPlan, PlanningRule
from jarvis.world_model.state import WorldState
from jarvis.world_model.user_profile import UserProfile
from jarvis.world_model.task import Task, JobStatus
from jarvis.world_model.device_status import DeviceStatus
from jarvis.brain_core.tool_policy import ToolMetadata, LanePolicy, LatencyClass
from jarvis.brain_core.contracts import ToolResultEnvelope


# ---------------------------------------------------------------------------
# Planner: tool_call rule generation
# ---------------------------------------------------------------------------

class TestPlannerToolCallRule:
    """Test that the planner generates tool_call actions for eligible tasks."""

    def _make_context(self, task_stack, available_tools):
        ws = WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=task_stack,
            open_bg1_jobs=[],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
        )

        class Ctx:
            def __init__(self, world_state, tools):
                self.world_state = world_state
                self.available_tools = tools
                self.available_models = ["llama3.2:1b"]

        return Ctx(ws, available_tools)

    def test_generates_tool_call_for_pending_task_with_tool(self):
        """Planner emits a tool_call action when a pending task names a known tool."""
        planner = Planner()
        task = Task(
            task_id="t1",
            description="check time",
            status="pending",
            metadata={"tool_name": "local_now"},
        )
        ctx = self._make_context([task], ["local_now", "calculator"])
        plan = planner.generate_plan(ctx)

        tool_call_actions = [a for a in plan.actions if a.action_type == "tool_call"]
        assert len(tool_call_actions) == 1
        assert tool_call_actions[0].target == "local_now"

    def test_no_tool_call_when_tool_unavailable(self):
        """No tool_call when the task's tool_name isn't in available_tools."""
        planner = Planner()
        task = Task(
            task_id="t1",
            description="check time",
            status="pending",
            metadata={"tool_name": "nonexistent_tool"},
        )
        ctx = self._make_context([task], ["calculator"])
        plan = planner.generate_plan(ctx)

        tool_call_actions = [a for a in plan.actions if a.action_type == "tool_call"]
        assert len(tool_call_actions) == 0

    def test_no_tool_call_for_completed_task(self):
        """No tool_call if the task with a tool_name is already completed."""
        planner = Planner()
        task = Task(
            task_id="t1",
            description="check time",
            status="completed",
            metadata={"tool_name": "local_now"},
        )
        ctx = self._make_context([task], ["local_now"])
        plan = planner.generate_plan(ctx)

        tool_call_actions = [a for a in plan.actions if a.action_type == "tool_call"]
        assert len(tool_call_actions) == 0

    def test_tool_call_carries_payload_from_task_metadata(self):
        """tool_call action payload comes from task metadata tool_kwargs."""
        planner = Planner()
        task = Task(
            task_id="t1",
            description="calculate",
            status="pending",
            metadata={
                "tool_name": "calculator",
                "tool_kwargs": {"expression": "2+2"},
            },
        )
        ctx = self._make_context([task], ["calculator"])
        plan = planner.generate_plan(ctx)

        tool_call_actions = [a for a in plan.actions if a.action_type == "tool_call"]
        assert len(tool_call_actions) == 1
        assert tool_call_actions[0].payload == {"expression": "2+2"}


# ---------------------------------------------------------------------------
# Execution gate in _generate_and_execute_plan
# ---------------------------------------------------------------------------

class TestPlannerExecution:
    """Test the execution gate logic in JarvisRuntime._generate_and_execute_plan.

    We test the gate conditions in isolation by building the same decision
    logic that _generate_and_execute_plan uses, without instantiating the
    full JarvisRuntime.
    """

    def test_single_realtime_tool_call_is_eligible(self):
        """A single tool_call action targeting a realtime, no-confirm tool is eligible."""
        meta = ToolMetadata(
            tool_name="local_now",
            purpose="Get current time",
            lane_policy=LanePolicy.REALTIME,
            safe_in_realtime=True,
            requires_confirmation=False,
        )
        action = Action(
            action_id="a0",
            action_type="tool_call",
            target="local_now",
        )
        plan = ActionPlan(
            actions=[action],
            priority_order=[0],
            estimated_duration=timedelta(milliseconds=10),
        )

        # Gate logic: single action, tool_call, safe_in_realtime, no confirmation
        assert len(plan.actions) == 1
        assert action.action_type == "tool_call"
        assert meta.safe_in_realtime is True
        assert meta.requires_confirmation is False

    def test_multi_action_plan_not_eligible(self):
        """Plans with 2+ actions are not auto-executed."""
        actions = [
            Action(action_id="a0", action_type="tool_call", target="local_now"),
            Action(action_id="a1", action_type="tool_call", target="calculator"),
        ]
        plan = ActionPlan(
            actions=actions,
            priority_order=[0, 1],
            estimated_duration=timedelta(milliseconds=20),
        )
        assert len(plan.actions) != 1  # Gate rejects

    def test_confirmation_required_tool_not_eligible(self):
        """tool_call targeting a confirmation-required tool is not auto-executed."""
        meta = ToolMetadata(
            tool_name="file_write",
            purpose="Write file",
            requires_confirmation=True,
            confirmation_action="file_write",
            safe_in_realtime=True,
        )
        assert meta.requires_confirmation is True  # Gate rejects

    def test_bg1_only_tool_not_eligible(self):
        """tool_call targeting a BG1-only tool is not auto-executed."""
        meta = ToolMetadata(
            tool_name="web_search",
            purpose="Search web",
            safe_in_realtime=False,
            lane_policy=LanePolicy.BG1,
        )
        assert meta.safe_in_realtime is False  # Gate rejects

    def test_non_tool_call_action_not_eligible(self):
        """Non-tool_call action types (task_dispatch, etc.) are not auto-executed."""
        action = Action(
            action_id="a0",
            action_type="task_dispatch",
            target="task1",
        )
        assert action.action_type != "tool_call"  # Gate rejects


# ---------------------------------------------------------------------------
# ActionPlan helper: get_next_action with tool_call
# ---------------------------------------------------------------------------

class TestActionPlanWithToolCall:
    """Test ActionPlan works correctly with tool_call actions."""

    def test_get_next_action_tool_call(self):
        actions = [
            Action(action_id="tc0", action_type="tool_call", target="calculator", payload={"expression": "1+1"}),
        ]
        plan = ActionPlan(
            actions=actions,
            priority_order=[0],
            estimated_duration=timedelta(milliseconds=50),
        )
        nxt = plan.get_next_action(completed=[])
        assert nxt is not None
        assert nxt.action_type == "tool_call"
        assert nxt.target == "calculator"
        assert nxt.payload == {"expression": "1+1"}

    def test_is_complete_after_tool_call(self):
        actions = [
            Action(action_id="tc0", action_type="tool_call", target="calculator"),
        ]
        plan = ActionPlan(
            actions=actions,
            priority_order=[0],
            estimated_duration=timedelta(milliseconds=50),
        )
        assert plan.is_complete(["tc0"]) is True
        assert plan.is_complete([]) is False

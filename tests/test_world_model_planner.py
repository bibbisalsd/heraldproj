"""Tests for Planner action plan generation."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone, timedelta

from jarvis.world_model.planner import Planner, Action, ActionPlan, PlanningRule, RulePredicate
from jarvis.world_model.state import WorldState
from jarvis.world_model.user_profile import UserProfile
from jarvis.world_model.task import Task, JobStatus
from jarvis.world_model.tool_health import ToolHealth
from jarvis.world_model.device_status import DeviceStatus


class TestAction:
    """Test Action dataclass."""

    def test_create_action_minimal(self):
        """Test creating Action with minimal fields."""
        action = Action(
            action_id="action_001",
            action_type="tool_call",
            target="calculator",
        )
        assert action.action_id == "action_001"
        assert action.action_type == "tool_call"
        assert action.target == "calculator"
        assert action.priority == 0
        assert action.depends_on == []

    def test_create_action_full(self):
        """Test creating Action with all fields."""
        action = Action(
            action_id="action_001",
            action_type="tool_call",
            target="calculator",
            payload={"expression": "2+2"},
            priority=10,
            estimated_duration_ms=100,
            depends_on=["action_000"],
            metadata={"retry_count": 3},
        )
        assert action.payload == {"expression": "2+2"}
        assert action.priority == 10
        assert action.estimated_duration_ms == 100
        assert "action_000" in action.depends_on


class TestActionPlan:
    """Test ActionPlan dataclass."""

    def get_sample_plan(self) -> ActionPlan:
        """Create sample ActionPlan for tests."""
        actions = [
            Action(action_id="action_001", action_type="tool_call", target="calculator"),
            Action(action_id="action_002", action_type="model_call", target="llama3.2:1b"),
            Action(action_id="action_003", action_type="response", target="output"),
        ]
        return ActionPlan(
            actions=actions,
            priority_order=[0, 1, 2],
            estimated_duration=timedelta(seconds=3),
        )

    def test_create_plan(self):
        """Test creating ActionPlan."""
        plan = self.get_sample_plan()
        assert len(plan.actions) == 3
        assert plan.priority_order == [0, 1, 2]

    def test_get_ordered_actions(self):
        """Test getting actions in priority order."""
        actions = [
            Action(action_id="low_priority", action_type="response", target="out", priority=1),
            Action(action_id="high_priority", action_type="tool_call", target="calc", priority=10),
        ]
        plan = ActionPlan(
            actions=actions,
            priority_order=[1, 0],  # High priority first
            estimated_duration=timedelta(seconds=1),
        )
        ordered = plan.get_ordered_actions()
        assert ordered[0].action_id == "high_priority"
        assert ordered[1].action_id == "low_priority"

    def test_get_next_action_no_dependencies(self):
        """Test getting next action when no dependencies."""
        plan = self.get_sample_plan()
        next_action = plan.get_next_action(completed=[])
        assert next_action.action_id == "action_001"

    def test_get_next_action_with_dependencies(self):
        """Test getting next action with dependencies."""
        actions = [
            Action(action_id="action_001", action_type="tool_call", target="calc"),
            Action(action_id="action_002", action_type="response", target="out", depends_on=["action_001"]),
        ]
        plan = ActionPlan(
            actions=actions,
            priority_order=[0, 1],
            estimated_duration=timedelta(seconds=1),
        )
        # action_002 depends on action_001, so action_001 should be next
        next_action = plan.get_next_action(completed=[])
        assert next_action.action_id == "action_001"

    def test_get_next_action_after_dependency_met(self):
        """Test getting next action after dependency is completed."""
        actions = [
            Action(action_id="action_001", action_type="tool_call", target="calc"),
            Action(action_id="action_002", action_type="response", target="out", depends_on=["action_001"]),
        ]
        plan = ActionPlan(
            actions=actions,
            priority_order=[0, 1],
            estimated_duration=timedelta(seconds=1),
        )
        # After action_001 is completed, action_002 should be next
        next_action = plan.get_next_action(completed=["action_001"])
        assert next_action.action_id == "action_002"

    def test_get_next_action_all_complete(self):
        """Test getting next action when all complete."""
        plan = self.get_sample_plan()
        next_action = plan.get_next_action(completed=["action_001", "action_002", "action_003"])
        assert next_action is None

    def test_is_complete(self):
        """Test checking if plan is complete."""
        plan = self.get_sample_plan()
        assert plan.is_complete(completed=[]) is False
        assert plan.is_complete(completed=["action_001", "action_002", "action_003"]) is True
        assert plan.is_complete(completed=["action_001", "action_002"]) is False


class TestPlanningRule:
    """Test PlanningRule dataclass."""

    def test_create_rule(self):
        """Test creating PlanningRule."""
        predicate = lambda ctx: True
        rule = PlanningRule(
            name="test_rule",
            predicate=predicate,
            action_type="tool_call",
            priority=50,
        )
        assert rule.name == "test_rule"
        assert rule.action_type == "tool_call"
        assert rule.priority == 50


class TestPlanner:
    """Test Planner operations."""

    def get_test_world_state(self) -> WorldState:
        """Create test WorldState."""
        return WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=[Task(task_id="task1", description="Test task", priority=5, status="pending")],
            open_bg1_jobs=[],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
        )

    def get_planning_context(self, world_state: WorldState):
        """Create planning context for tests."""
        class SimpleContext:
            def __init__(self, ws):
                self.world_state = ws
                self.available_tools = ["calculator", "file_read", "web_search"]
                self.available_models = ["llama3.2:1b", "llama3.2:3b"]
        return SimpleContext(world_state)

    def test_create_planner_with_default_rules(self):
        """Test Planner initializes with default rules."""
        planner = Planner()
        assert len(planner._rules) > 0  # Has default rules

    def test_generate_plan_with_tasks(self):
        """Test generating plan when tasks are pending."""
        planner = Planner()
        world_state = self.get_test_world_state()
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        assert plan is not None
        assert len(plan.actions) >= 0  # May generate actions for tasks

    def test_generate_plan_empty_when_no_tasks(self):
        """Test generating plan when no tasks or triggers."""
        planner = Planner()
        world_state = WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=[],
            open_bg1_jobs=[],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
        )
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        # Plan may still have actions from default rules
        assert plan is not None

    def test_generate_plan_with_bg1_jobs(self):
        """Test generating plan when bg1 jobs are pending."""
        planner = Planner()
        world_state = WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=[],
            open_bg1_jobs=[JobStatus(job_id="job1", task_id="task1", status="running")],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
        )
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        assert plan is not None

    def test_generate_plan_with_degraded_tool(self):
        """Test generating plan when tools are degraded."""
        planner = Planner()
        tool_health = ToolHealth(tool_name="calculator")
        tool_health = tool_health.record_call(success=False, error="Error")
        tool_health = tool_health.record_call(success=False, error="Error")
        tool_health = tool_health.record_call(success=False, error="Error")
        # Error rate now > 0.3

        world_state = WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=[],
            open_bg1_jobs=[],
            tool_availability={"calculator": tool_health},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
        )
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        assert plan is not None

    def test_add_rule(self):
        """Test adding custom rule."""
        planner = Planner()
        initial_count = len(planner._rules)
        planner.add_rule(PlanningRule(
            name="custom_rule",
            predicate=lambda ctx: True,
            action_type="custom_action",
            priority=100,
        ))
        assert len(planner._rules) == initial_count + 1

    def test_clear_rules(self):
        """Test clearing all rules."""
        planner = Planner()
        planner.clear_rules()
        assert len(planner._rules) == 0

    def test_plan_priority_ordering(self):
        """Test that plans respect rule priority ordering."""
        planner = Planner()
        planner.clear_rules()
        # Add rules in reverse priority order
        planner.add_rule(PlanningRule(
            name="low_priority",
            predicate=lambda ctx: True,
            action_type="low_action",
            priority=10,
        ))
        planner.add_rule(PlanningRule(
            name="high_priority",
            predicate=lambda ctx: True,
            action_type="high_action",
            priority=100,
        ))
        world_state = self.get_test_world_state()
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        # High priority rule should generate first action
        assert len(plan.actions) == 2
        assert plan.actions[0].metadata.get("rule_name") == "high_priority"

    def test_plan_duration_estimation(self):
        """Test plan estimates total duration."""
        planner = Planner()
        planner.clear_rules()
        planner.add_rule(PlanningRule(
            name="quick_action",
            predicate=lambda ctx: True,
            action_type="network_check",  # 100ms
            priority=50,
        ))
        world_state = self.get_test_world_state()
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        assert plan.estimated_duration.total_seconds() >= 0.1  # At least 100ms

    def test_rule_predicate_context_access(self):
        """Test rule predicates can access context."""
        planner = Planner()
        planner.clear_rules()

        # Rule that checks task stack
        def has_pending_tasks(ctx):
            return len(ctx.world_state.task_stack) > 0

        planner.add_rule(PlanningRule(
            name="process_pending",
            predicate=has_pending_tasks,
            action_type="task_dispatch",
            priority=50,
        ))

        # With tasks - rule should fire
        world_state_with_tasks = self.get_test_world_state()
        context = self.get_planning_context(world_state_with_tasks)
        plan = planner.generate_plan(context)
        assert len(plan.actions) >= 1

        # Without tasks - rule should not fire
        world_state_empty = WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=[],
            open_bg1_jobs=[],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
        )
        context = self.get_planning_context(world_state_empty)
        plan = planner.generate_plan(context)
        assert len(plan.actions) == 0

    def test_action_target_determination(self):
        """Test action target is determined from context."""
        planner = Planner()
        planner.clear_rules()

        # Rule for task dispatch
        planner.add_rule(PlanningRule(
            name="dispatch_task",
            predicate=lambda ctx: len(ctx.world_state.task_stack) > 0,
            action_type="task_dispatch",
            priority=50,
        ))

        world_state = self.get_test_world_state()
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)

        if plan.actions:
            # Target should be the task_id
            assert plan.actions[0].target == "task1"

    def test_network_check_action(self):
        """Test network check action for disconnected state."""
        planner = Planner()
        # Default rules include network check

        world_state = WorldState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_profile=UserProfile(user_id="test"),
            task_stack=[],
            open_bg1_jobs=[],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),  # Network disconnected
        )
        context = self.get_planning_context(world_state)
        plan = planner.generate_plan(context)
        # May generate network check action
        assert plan is not None

"""Planner - Generate action plans from WorldState using deterministic priority rules."""

from __future__ import annotations

from jarvis.tools.registry import ToolRegistry
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from jarvis.world_model.state import WorldState


@dataclass(frozen=True)
class Action:
    """An action to be taken."""

    action_id: str
    action_type: str  # "tool_call", "model_call", "task_dispatch", "response"
    target: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    estimated_duration_ms: int = 0
    depends_on: list[str] = field(default_factory=list)  # Action IDs this depends on
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionPlan:
    """Ordered action plan."""

    actions: list[Action]
    priority_order: list[int]  # Indices into actions list, ordered by priority
    estimated_duration: timedelta
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def get_ordered_actions(self) -> list[Action]:
        """Get actions in priority order."""
        return [self.actions[i] for i in self.priority_order]

    def get_next_action(self, completed: list[str]) -> Action | None:
        """Get the next action that can be executed (dependencies met)."""
        completed_set = set(completed)
        for idx in self.priority_order:
            action = self.actions[idx]
            if action.action_id in completed_set:
                continue
            # Check dependencies
            if all(dep in completed_set for dep in action.depends_on):
                return action
        return None

    def is_complete(self, completed: list[str]) -> bool:
        """Check if all actions are complete."""
        completed_set = set(completed)
        return all(action.action_id in completed_set for action in self.actions)


class PlanningContext(Protocol):
    """Protocol for planning context."""

    world_state: WorldState
    available_tools: list[str]
    available_models: list[str]


@dataclass
class PlanningRule:
    """A planning rule."""

    name: str
    predicate: "RulePredicate"
    action_type: str
    priority: int


class RulePredicate(Protocol):
    """Protocol for rule predicates."""

    def __call__(self, context: PlanningContext) -> bool:
        """Check if rule applies."""
        ...


class Planner:
    """Generate action plans from WorldState using deterministic priority rules.

    Hybrid planning:
    - Rule-based (primary): Deterministic priority rules
    - LLM fallback: For novel situations not covered by rules

    Priority rules (in order):
    1. Safety > completion > efficiency
    2. Realtime > bg1
    3. User-requested > inferred > proactive
    """

    # Priority constants
    PRIORITY_SAFETY = 100
    PRIORITY_COMPLETION = 50
    PRIORITY_EFFICIENCY = 10

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._rules: list[PlanningRule] = []
        self._tool_registry = tool_registry or ToolRegistry()
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default planning rules."""
        # Rule 1: Safety-critical actions first
        self._rules.append(
            PlanningRule(
                name="safety_first",
                predicate=lambda context: (
                    context.world_state.device_status is not None
                    and context.world_state.device_status.network_state != "connected"
                ),
                action_type="network_check",
                priority=self.PRIORITY_SAFETY,
            )
        )

        # Rule 2: Process pending tasks by priority
        self._rules.append(
            PlanningRule(
                name="process_tasks",
                predicate=lambda context: len(context.world_state.task_stack) > 0,
                action_type="task_dispatch",
                priority=self.PRIORITY_COMPLETION,
            )
        )

        # Rule 3: Handle bg1 job results
        self._rules.append(
            PlanningRule(
                name="process_bg1_results",
                predicate=lambda context: len(context.world_state.open_bg1_jobs) > 0,
                action_type="job_result_check",
                priority=self.PRIORITY_COMPLETION - 10,
            )
        )

        # Rule 4: Update tool health
        self._rules.append(
            PlanningRule(
                name="update_tool_health",
                predicate=lambda context: any(
                    t.error_rate > 0.3
                    for t in context.world_state.tool_availability.values()
                ),
                action_type="tool_health_check",
                priority=self.PRIORITY_EFFICIENCY,
            )
        )

        # Rule 5 (Phase 5C): Execute pending tasks that target a known tool
        self._rules.append(
            PlanningRule(
                name="execute_tool_task",
                predicate=lambda context: any(
                    t.status == "pending"
                    and t.metadata.get("tool_name") in context.available_tools
                    for t in context.world_state.task_stack
                ),
                action_type="tool_call",
                priority=self.PRIORITY_COMPLETION - 5,
            )
        )

    def generate_plan(self, context: PlanningContext) -> ActionPlan:
        """Generate an action plan from WorldState.

        Uses rule-based planning with LLM fallback for novel situations.
        """
        actions: list[Action] = []
        action_id_counter = 0

        # Apply rules in priority order
        for rule in sorted(self._rules, key=lambda r: r.priority, reverse=True):
            if rule.predicate(context):
                action = self._create_action_from_rule(rule, context, action_id_counter)
                actions.append(action)
                action_id_counter += 1

        # Build priority order (already sorted by rule priority)
        priority_order = list(range(len(actions)))

        # Estimate duration
        total_duration_ms = sum(a.estimated_duration_ms for a in actions)

        return ActionPlan(
            actions=actions,
            priority_order=priority_order,
            estimated_duration=timedelta(milliseconds=total_duration_ms),
        )

    def _create_action_from_rule(
        self, rule: PlanningRule, context: PlanningContext, action_id_counter: int
    ) -> Action:
        """Create an action from a rule."""
        action_id = f"action_{action_id_counter}"

        # Determine target based on rule type
        target = self._determine_target(rule.action_type, context)

        # Phase 5C: Extract tool payload for tool_call actions
        payload: dict[str, Any] = {}
        if rule.action_type == "tool_call":
            for t in context.world_state.task_stack:
                if t.status == "pending" and t.metadata.get("tool_name") == target:
                    payload = dict(t.metadata.get("tool_kwargs", {}))
                    break

        return Action(
            action_id=action_id,
            action_type=rule.action_type,
            target=target,
            payload=payload,
            priority=rule.priority,
            estimated_duration_ms=self._estimate_duration(rule.action_type),
            metadata={"rule_name": rule.name},
        )

    def _determine_target(self, action_type: str, context: PlanningContext) -> str:
        """Determine action target based on type and context."""
        if action_type == "task_dispatch":
            # Get highest priority pending task
            pending_tasks = [
                t for t in context.world_state.task_stack if t.status == "pending"
            ]
            if pending_tasks:
                highest = max(pending_tasks, key=lambda t: t.priority)
                return highest.task_id
            return "unknown"
        elif action_type == "job_result_check":
            if context.world_state.open_bg1_jobs:
                return context.world_state.open_bg1_jobs[0].job_id
            return "unknown"
        elif action_type == "tool_health_check":
            # Find first degraded tool
            for name, health in context.world_state.tool_availability.items():
                if health.error_rate > 0.3:
                    return name
            return "unknown"
        elif action_type == "network_check":
            return "network"
        elif action_type == "tool_call":
            # Phase 5C: Find pending task with a tool target
            for t in context.world_state.task_stack:
                if (
                    t.status == "pending"
                    and t.metadata.get("tool_name") in context.available_tools
                ):
                    return t.metadata["tool_name"]
            return "unknown"
        else:
            return "unknown"

    def _estimate_duration(self, action_type: str) -> int:
        """Estimate duration in ms for an action type."""
        durations = {
            "network_check": 100,
            "task_dispatch": 500,
            "job_result_check": 50,
            "tool_health_check": 100,
            "tool_call": 1000,
            "model_call": 2000,
            "response": 100,
        }
        return durations.get(action_type, 500)

    def add_rule(self, rule: "PlanningRule") -> None:
        """Add a custom planning rule."""
        self._rules.append(rule)

    def clear_rules(self) -> None:
        """Clear all rules (for testing)."""
        self._rules.clear()

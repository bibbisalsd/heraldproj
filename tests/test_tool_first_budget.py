from __future__ import annotations
from jarvis.observability.metrics import ToolFirstBudget


def test_tool_first_budget_hits_target_band():
    budget = ToolFirstBudget()
    resolutions = (
        ["template"] * 20
        + ["tool_only"] * 20
        + ["tool_plus_renderer"] * 20
        + ["model_reasoning"] * 20
    )
    for item in resolutions:
        budget.record(item)

    ratio = budget.ratio()
    assert 0.70 <= ratio <= 0.85

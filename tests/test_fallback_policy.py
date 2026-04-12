from __future__ import annotations
from jarvis.brain_core.fallback_policy import FallbackPolicy


def test_fallback_policy_renderer_uses_template_strategy():
    policy = FallbackPolicy()
    action = policy.resolve(component="renderer", error_type="timeout", context={})
    assert action.strategy == "template_response"


def test_fallback_policy_output_sink_switches_to_next_sink():
    policy = FallbackPolicy()
    action = policy.resolve(component="output_sink", error_type="delivery_failed", context={})
    assert action.strategy == "next_sink"

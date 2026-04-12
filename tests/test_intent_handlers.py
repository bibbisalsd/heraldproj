from __future__ import annotations

from types import SimpleNamespace

from jarvis.brain_core.intent_handlers import (
    IntentHandlerRegistry,
    build_default_registry,
    handle_addon_disable,
    handle_addon_enable,
    handle_name_recognition,
)
from jarvis.brain_core.addon_manager import AddonManager
from jarvis.brain_core.addon_registry import AddonRegistry
from jarvis.brain_core.contracts import AddonManifest


def test_registry_register_and_resolve() -> None:
    registry = IntentHandlerRegistry()
    sentinel = object()

    def handler(env, decision, services):
        del env, decision, services
        return sentinel

    registry.register("time_query", handler)
    env = SimpleNamespace(text="what time is it")
    decision = SimpleNamespace(intent="time_query")

    result = registry.resolve(env, decision, {})
    assert result is sentinel


def test_registry_unknown_intent_returns_none() -> None:
    registry = IntentHandlerRegistry()
    env = SimpleNamespace(text="unknown")
    decision = SimpleNamespace(intent="not_registered")
    assert registry.resolve(env, decision, {}) is None


def test_pre_intent_handler_priority() -> None:
    registry = IntentHandlerRegistry()
    calls: list[str] = []

    def pre_handler(env, decision, services):
        del env, decision, services
        calls.append("pre")
        return "pre-result"

    def intent_handler(env, decision, services):
        del env, decision, services
        calls.append("intent")
        return "intent-result"

    registry.register_pre_intent(pre_handler)
    registry.register("time_query", intent_handler)
    env = SimpleNamespace(text="anything")
    decision = SimpleNamespace(intent="time_query")

    assert registry.resolve(env, decision, {}) == "pre-result"
    assert calls == ["pre"]


def test_build_default_registry_has_all_intents() -> None:
    registry = build_default_registry()
    expected = {
        "time_query",
        "status",
        "job_status",
        "job_cancel",
        "notify_when_free",
        "recall_name",
        "addon_enable",
        "addon_disable",
    }
    assert expected.issubset(set(registry._handlers.keys()))


def test_name_recognition_handler() -> None:
    remembered: list[tuple[str, str, float]] = []

    class MemoryStub:
        def remember(self, key: str, value: str, confidence: float = 1.0) -> bool:
            remembered.append((key, value, confidence))
            return True

    env = SimpleNamespace(text="my name is Alex")
    decision = SimpleNamespace(intent=None)
    services = {"memory": MemoryStub()}

    result = handle_name_recognition(env, decision, services)
    assert result is not None
    assert result.text == "I inferred your name is Alex, is that correct?"
    assert result.resolved_by == "tool_only"
    assert result.memory_items == []
    assert "ask_for_confirmation" in result.renderer_constraints


def test_name_recognition_no_match() -> None:
    remembered: list[tuple[str, str, float]] = []

    class MemoryStub:
        def remember(self, key: str, value: str, confidence: float = 1.0) -> bool:
            remembered.append((key, value, confidence))
            return True

    env = SimpleNamespace(text="hello there")
    decision = SimpleNamespace(intent=None)
    services = {"memory": MemoryStub()}

    result = handle_name_recognition(env, decision, services)
    assert result is None
    assert remembered == []


def _discord_manager() -> tuple[AddonManager, AddonRegistry]:
    registry = AddonRegistry()
    manager = AddonManager(registry)
    manifest = AddonManifest(
        addon_id="discord",
        addon_name="Discord",
        version="0.1.0",
        capability_summary="Discord bridge",
    )
    manager.discover([manifest])
    # Mock load to avoid module import failure in tests
    manager.states["discord"] = "LOADED"
    return manager, registry


def test_addon_enable_handler_enables_known_addon() -> None:
    manager, registry = _discord_manager()
    env = SimpleNamespace(text="enable addon discord")
    decision = SimpleNamespace(intent="addon_enable")

    result = handle_addon_enable(env, decision, {"addon_manager": manager, "addon_registry": registry})

    assert result.text == "Enabled addon discord."
    assert manager.states["discord"] == "ENABLED"


def test_addon_disable_handler_disables_enabled_addon() -> None:
    manager, registry = _discord_manager()
    manager.start("discord")
    env = SimpleNamespace(text="disable addon discord")
    decision = SimpleNamespace(intent="addon_disable")

    result = handle_addon_disable(env, decision, {"addon_manager": manager, "addon_registry": registry})

    assert result.text == "Disabled addon discord."
    assert manager.states["discord"] == "DISABLED"

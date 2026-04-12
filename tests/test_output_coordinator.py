from __future__ import annotations
from jarvis.brain_core.contracts import RenderedReply
from jarvis.brain_core.output_coordinator import OutputCoordinator


def test_output_coordinator_uses_primary_when_healthy():
    coordinator = OutputCoordinator()
    reply = RenderedReply(text="hello", sink="local_voice")
    result = coordinator.deliver(reply, {"local_voice": True})
    assert result.delivered is True
    assert result.sink == "local_voice"


def test_output_coordinator_falls_back_when_primary_unhealthy():
    coordinator = OutputCoordinator()
    reply = RenderedReply(text="hello", sink="local_voice")
    result = coordinator.deliver(
        reply,
        {"local_voice": False, "active_addon_text": True, "local_text_log": True},
    )
    assert result.delivered is True
    assert result.sink == "active_addon_text"


def test_output_coordinator_prefers_text_fallbacks_over_voice_for_text_reply():
    coordinator = OutputCoordinator()
    reply = RenderedReply(text="hello", sink="discord_text")
    result = coordinator.deliver(
        reply,
        {"discord_text": False, "local_voice": True, "local_text_log": True},
    )
    assert result.delivered is True
    assert result.sink == "local_text_log"

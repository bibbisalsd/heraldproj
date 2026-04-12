from __future__ import annotations
import os

from jarvis.brain_core.cllm_renderer import CLLMRenderer
from jarvis.brain_core.response_compiler import ResponsePacket
from jarvis.main import JarvisRuntime


def test_renderer_returns_degraded_message_when_flag_set(monkeypatch):
    monkeypatch.setenv("JARVIS_DEGRADED_MODE", "true")
    packet = ResponsePacket(user_text="status", facts=["brain:fact:a"], constraints=[], tone="neutral", length_hint="short")
    text = CLLMRenderer().render(packet)
    assert "degraded mode" in text.lower()


def test_runtime_sets_degraded_mode_when_model_not_ready(monkeypatch):
    monkeypatch.delenv("JARVIS_DEGRADED_MODE", raising=False)
    rt = JarvisRuntime()
    state = rt.startup(model_ready=False)
    assert state.degraded_mode is True
    assert os.getenv("JARVIS_DEGRADED_MODE", "false").lower() == "true"

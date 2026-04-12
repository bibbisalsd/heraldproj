from __future__ import annotations
from jarvis.models.ollama_client import OllamaRunResult
from jarvis.brain_core.cllm_renderer import CLLMRenderer
from jarvis.brain_core.response_compiler import ResponsePacket


def test_renderer_strips_internal_prefixes_in_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("JARVIS_DEGRADED_MODE", "false")
    monkeypatch.setattr(
        "jarvis.models.ollama_client.OllamaClient.run",
        lambda self, prompt: OllamaRunResult(ok=False, text="", error="unavailable"),
    )
    packet = ResponsePacket(
        user_text="status",
        facts=["brain:Jarvis is online.", "tool:local_time:3:42pm", "memory:user_name:alex", "job_status:RUNNING"],
        constraints=["renderer_only_no_new_facts"],
        tone="neutral",
        length_hint="short",
    )
    result = CLLMRenderer().render(packet)
    text = result["text"]
    assert "Jarvis is online." in text
    assert "local_time:3:42pm" in text
    assert "user_name:alex" in text
    assert "RUNNING" in text
    assert "brain:" not in text
    assert "tool:" not in text
    assert "memory:" not in text
    assert "job_status:" not in text


def test_renderer_returns_degraded_message(monkeypatch):
    monkeypatch.setenv("JARVIS_DEGRADED_MODE", "true")
    packet = ResponsePacket(
        user_text="status",
        facts=["brain:Jarvis is online."],
        constraints=["renderer_only_no_new_facts"],
        tone="neutral",
        length_hint="short",
    )
    result = CLLMRenderer().render(packet)
    text = result["text"]
    assert "degraded mode" in text.lower()


def test_renderer_rejects_invalid_packet_limit(monkeypatch):
    monkeypatch.setenv("JARVIS_DEGRADED_MODE", "false")
    packet = ResponsePacket(
        user_text="status",
        facts=["brain:Jarvis is online."],
        constraints=["renderer_only_no_new_facts"],
        tone="neutral",
        length_hint="short",
        max_packet_tokens=0,
    )
    result = CLLMRenderer().render(packet)
    text = result["text"]
    assert text == "Unable to render packet."

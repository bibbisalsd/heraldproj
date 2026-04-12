from __future__ import annotations

from jarvis.brain_core.cllm_renderer import CLLMRenderer


def render_text(packet) -> str:
    return CLLMRenderer().render(packet)

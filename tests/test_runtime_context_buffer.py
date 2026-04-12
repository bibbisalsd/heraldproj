from __future__ import annotations
from jarvis.main import JarvisRuntime


def test_runtime_appends_turns_to_conversation_buffer():
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)

    runtime.run_turn("hello")
    runtime.run_turn("status")

    recent = runtime.conversation_buffer.recent()
    assert runtime.conversation_buffer.size >= 2
    assert recent[-1].user_text == "status"

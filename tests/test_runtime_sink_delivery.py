from __future__ import annotations

import json

from jarvis.main import JarvisRuntime


def test_runtime_skips_local_tts_for_discord_text(monkeypatch) -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)
    spoken: list[str] = []

    monkeypatch.setattr(runtime.tts, "speak_reliable", lambda text: spoken.append(text))

    result = runtime.run_turn("status", source="discord_text")

    assert result["sink"] == "discord_text"
    assert spoken == []


def test_runtime_uses_local_tts_for_local_voice(monkeypatch) -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)
    spoken: list[str] = []

    monkeypatch.setattr(runtime.tts, "speak_reliable", lambda text: spoken.append(text))

    result = runtime.run_turn("status", source="local_mic")

    assert result["sink"] == "local_voice"
    assert len(spoken) == 1


def test_runtime_writes_local_text_log_when_selected(tmp_path, monkeypatch) -> None:
    runtime = JarvisRuntime()
    runtime.config = runtime.config.__class__(**{**vars(runtime.config), "events_log_dir": str(tmp_path / "logs")})
    runtime.startup(model_ready=True)
    spoken: list[str] = []

    monkeypatch.setattr(runtime.tts, "speak_reliable", lambda text: spoken.append(text))
    monkeypatch.setattr(runtime, "_select_sink", lambda _source: "local_text_log")
    monkeypatch.setattr(
        runtime,
        "_build_sink_status",
        lambda **_kwargs: {
            "local_voice": False,
            "discord_voice": False,
            "discord_text": False,
            "active_addon_text": False,
            "local_text_log": True,
        },
    )

    result = runtime.run_turn("status", source="local_mic")

    assert result["sink"] == "local_text_log"
    assert spoken == []

    log_files = list((tmp_path / "logs").glob("jarvis_output_*.jsonl"))
    assert len(log_files) == 1
    payload = json.loads(log_files[0].read_text(encoding="utf-8").strip())
    assert payload["sink"] == "local_text_log"
    assert payload["source"] == "local_mic"
    assert "online" in payload["text"].lower()


def test_runtime_sink_status_is_contextual_for_discord_text() -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)

    local_status = runtime._build_sink_status(source="local_mic")
    discord_status = runtime._build_sink_status(source="discord_text")

    assert local_status["discord_text"] is False
    assert discord_status["discord_text"] is True


def test_runtime_can_enable_and_disable_reference_addon() -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)
    
    # Mock addon manager
    runtime.addon_manager.states["discord"] = "DISABLED"
    def mock_start(aid):
        runtime.addon_manager.states[aid] = "ENABLED"
        return True
    def mock_stop(aid):
        runtime.addon_manager.states[aid] = "DISABLED"
        return True
    runtime.addon_manager.start = mock_start # type: ignore
    runtime.addon_manager.stop = mock_stop # type: ignore
    
    enable_result = runtime.run_turn("enable addon discord", source="local_mic")
    disable_result = runtime.run_turn("disable addon discord", source="local_mic")

    assert enable_result["intent"] == "addon_enable"
    assert enable_result["text"] == "Enabled addon discord."
    assert disable_result["intent"] == "addon_disable"
    assert disable_result["text"] == "Disabled addon discord."

from __future__ import annotations

from jarvis.brain_core.contracts import RawEvent
from jarvis.main import JarvisRuntime


def test_runtime_denies_guest_heavy_task_requests() -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)

    result = runtime.run_turn("please research this deeply", source="discord_text")

    assert result["lane"] == "realtime"
    assert "permission profile" in result["text"].lower()
    assert runtime.job_status.get_current() is None


def test_runtime_denies_guest_addon_control() -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)
    initial_state = runtime.addon_manager.states["discord"]

    result = runtime.run_turn("enable addon discord", source="discord_text")

    assert result["intent"] == "addon_enable"
    assert "permission profile" in result["text"].lower()
    assert runtime.addon_manager.states["discord"] == initial_state
    assert runtime.addon_manager.states["discord"] in {"LOADED", "DISABLED", "FAULTED"}


def test_runtime_denies_guest_memory_save(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("workspace rules", encoding="utf-8")
    monkeypatch.chdir(workspace)

    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)

    first = runtime.run_turn("my name is Sam", source="discord_text")
    second = runtime.run_turn("what is my name", source="local_mic")

    assert "permission profile" in first["text"].lower()
    assert "do not have your name saved" in second["text"].lower()


def test_runtime_denies_guest_cancel_request() -> None:
    runtime = JarvisRuntime()
    runtime.startup(model_ready=True)

    result = runtime.run_turn("cancel current heavy task", source="discord_text")

    assert result["intent"] == "job_cancel"
    assert "permission profile" in result["text"].lower()


def test_runtime_uses_addon_permission_mapper_for_addon_events(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_OWNER_IDS", "123")
    monkeypatch.setenv("DISCORD_TRUSTED_IDS", "456")
    
    # Reset the singleton in the permissions module so it re-reads the environment
    try:
        from addons.discord_addon import permissions
        permissions._initialized = False
    except ImportError:
        pass

    runtime = JarvisRuntime()
    owner_env = runtime.normalizer.normalize(
        RawEvent(
            source="addon",
            addon_id="discord",
            speaker_id="123",
            channel="discord_voice",
            payload="status",
        )
    )
    trusted_env = runtime.normalizer.normalize(
        RawEvent(
            source="addon",
            addon_id="discord",
            speaker_id="456",
            channel="discord_voice",
            payload="status",
        )
    )
    guest_env = runtime.normalizer.normalize(
        RawEvent(
            source="addon",
            addon_id="discord",
            speaker_id="someone_else",
            channel="discord_voice",
            payload="status",
        )
    )

    assert owner_env.profile == "owner"
    assert trusted_env.profile == "trusted"
    assert guest_env.profile == "guest"

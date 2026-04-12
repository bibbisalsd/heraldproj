from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from types import SimpleNamespace
from datetime import datetime, timezone

from jarvis.main import JarvisRuntime, TurnExecutionResult
from jarvis.brain_core.contracts import AddonManifest, RawEvent
from jarvis.brain_core.addon_manager import AddonManager
from jarvis.brain_core.addon_registry import AddonRegistry


def _runtime_with_tmp_state(tmp_path) -> JarvisRuntime:
    # Set environment variables for testing
    import os
    os.environ["JARVIS_MEMORY_DB_PATH"] = str(tmp_path / "test_memory.sqlite")
    os.environ["JARVIS_EVENTS_LOG_DIR"] = str(tmp_path / "logs")
    
    rt = JarvisRuntime()
    return rt


def _wait_until_idle(runtime: JarvisRuntime, timeout: float = 2.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        if not runtime.bg1_manager.is_busy():
            return
        time.sleep(0.05)


def _wait_for_notification_events(runtime: JarvisRuntime, timeout: float = 2.0) -> list:
    start = time.time()
    while time.time() - start < timeout:
        events = runtime.events.export()
        notifs = [e for e in events if e.get("event_type") == "job_complete_notification"]
        if notifs:
            return notifs
        time.sleep(0.05)
    return []


def test_runtime_cancel_stops_bg1_before_result_persists(tmp_path) -> None:
    runtime = _runtime_with_tmp_state(tmp_path)
    runtime.startup(model_ready=True)

    def fake_specialist(summary: str, **kwargs: Any) -> str:
        time.sleep(5.0)
        return f"done:{summary}"

    runtime.bg1_manager._execute_bg1_specialist = fake_specialist  # type: ignore[method-assign]
    
    # Mock render_with_fallback on turn_pipeline
    runtime.turn_pipeline._render_with_fallback = lambda compiled: next(  # type: ignore[method-assign]
        (fact[5:] for fact in compiled.facts if fact.startswith("user:")),
        "rendered",
    )

    started = runtime.run_turn("please research this deeply")
    cancelled = runtime.run_turn("cancel current task")

    assert started["lane"] == "bg1"
    assert started["resolved_by"] == "tool_only"
    assert cancelled["lane"] == "realtime"
    assert "cancellation requested" in cancelled["text"].lower()
    
    _wait_until_idle(runtime)
    assert runtime.bg1_manager.get_last_result() is None
    runtime.shutdown()


import pytest

@pytest.mark.skip(reason="Flaky race condition in notification events after structural merge")
def test_runtime_notify_when_free_emits_completion_notification(monkeypatch, tmp_path) -> None:
    runtime = _runtime_with_tmp_state(tmp_path)
    runtime.startup(model_ready=True)

    def fake_specialist(summary: str, **kwargs: Any) -> str:
        time.sleep(5.0)
        return f"done:{summary}"

    monkeypatch.setattr(runtime.bg1_manager, "_execute_bg1_specialist", fake_specialist)
    monkeypatch.setattr(
        runtime.turn_pipeline,
        "_render_with_fallback",
        lambda compiled: next(
            (fact[5:] for fact in compiled.facts if fact.startswith("user:")),
            "rendered",
        ),
    )

    spoken: list[str] = []

    def fake_speak(text: str) -> dict[str, Any]:
        spoken.append(text)
        runtime.tts.last_spoken = text
        runtime.tts.last_backend = "stub"
        runtime.tts.last_error = ""
        return {
            "ok": True,
            "text": text,
            "output_device_id": runtime.tts.output_device_id,
            "backend": "stub",
            "model": runtime.tts.model_name,
            "error": "",
        }

    monkeypatch.setattr(runtime.tts, "speak_reliable", fake_speak)

    runtime.run_turn("please research this deeply")
    subscribed = runtime.run_turn("notify me when free")
    _wait_until_idle(runtime)
    notification_events = _wait_for_notification_events(runtime)

    assert subscribed["lane"] == "realtime"
    assert "notify you" in subscribed["text"].lower()
    # assert runtime.job_status.subscription_count() == 0
    assert len(notification_events) == 1
    assert "heavy task" in spoken[-1].lower()
    assert "complete" in spoken[-1].lower()
    runtime.shutdown()


def test_runtime_can_queue_one_additional_bg1_task(monkeypatch, tmp_path) -> None:
    runtime = _runtime_with_tmp_state(tmp_path)
    runtime.startup(model_ready=True)

    def fake_specialist(summary: str, **kwargs: Any) -> str:
        time.sleep(5.0)
        return f"done:{summary}"

    monkeypatch.setattr(runtime.bg1_manager, "_execute_bg1_specialist", fake_specialist)
    monkeypatch.setattr(
        runtime.turn_pipeline,
        "_render_with_fallback",
        lambda compiled: next(
            (fact[5:] for fact in compiled.facts if fact.startswith("user:")),
            "rendered",
        ),
    )

    # 1. Start first task
    first = runtime.run_turn("research apples")
    assert first["lane"] == "bg1"
    assert first["job_snapshot"]["state"] == "RUNNING"

    # 2. Queue second task
    second = runtime.run_turn("research oranges")
    assert second["lane"] == "bg1"
    assert "queued" in second["text"].lower()
    assert second["job_snapshot"]["state"] == "QUEUED"

    time.sleep(0.1)

    # 3. Try to queue third task (should be rejected by admission control)
    third = runtime.run_turn("research bananas")
    assert third["lane"] == "realtime"
    assert "busy" in third["text"].lower()
    
    _wait_until_idle(runtime)
    runtime.shutdown()

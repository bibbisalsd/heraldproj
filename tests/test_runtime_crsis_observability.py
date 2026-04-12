from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from jarvis.config import build_default_config
from jarvis.main import JarvisRuntime


def _runtime_with_tmp_logs(monkeypatch, tmp_path: Path) -> JarvisRuntime:
    cfg = replace(build_default_config(), events_log_dir=str(tmp_path))
    monkeypatch.setattr("jarvis.main.build_default_config", lambda: cfg)
    return JarvisRuntime()


def test_runtime_startup_event_includes_crsis_snapshot_refs(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime_with_tmp_logs(monkeypatch, tmp_path)
    runtime.startup(model_ready=True)

    event = runtime.events.export()[-1]
    assert event["event_type"] == "runtime_startup"
    assert event["crsis_status"] == "ok"
    assert event["crsis_findings"] == 0
    assert event["crsis_snapshot_jsonl"]
    assert event["crsis_snapshot_latest"]
    assert Path(str(event["crsis_snapshot_jsonl"])).exists()
    assert Path(str(event["crsis_snapshot_latest"])).exists()


def test_runtime_startup_degraded_marks_crsis_critical(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime_with_tmp_logs(monkeypatch, tmp_path)
    runtime.startup(model_ready=False)

    event = runtime.events.export()[-1]
    assert event["event_type"] == "runtime_startup"
    assert event["degraded_mode_active"] is True
    assert event["crsis_status"] == "critical"
    assert int(event["crsis_findings"]) >= 1


def test_runtime_turn_event_includes_turn_correlated_crsis(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime_with_tmp_logs(monkeypatch, tmp_path)
    runtime.startup(model_ready=True)
    result = runtime.run_turn("status")

    events = runtime.events.export()
    turn_events = [event for event in events if event["turn_id"] == result["turn_id"]]
    assert len(turn_events) == 1
    event = turn_events[0]

    assert event["event_type"] == "turn_complete"
    assert event["lane_decision"] == result["lane"]
    assert event["crsis_status"] in {"ok", "warn", "critical"}
    assert event["crsis_snapshot_jsonl"]
    assert event["crsis_snapshot_latest"]
    assert Path(str(event["crsis_snapshot_jsonl"])).exists()
    assert Path(str(event["crsis_snapshot_latest"])).exists()

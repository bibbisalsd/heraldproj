from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from jarvis.observability.events import EventRecord, PersistentEventLogger


def _today_file(log_dir: str) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Path(log_dir) / f"jarvis_events_{today}.jsonl"


def _make_event(event_type: str = "turn_complete", turn_id: str = "test-001") -> EventRecord:
    return EventRecord.build(
        event_type=event_type,
        turn_id=turn_id,
        lane_decision="realtime",
        resolved_by="template",
        elapsed_ms=5,
        degraded_mode_active=False,
    )


def test_persistent_emit_creates_file(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "test_logs")
    logger = PersistentEventLogger(log_dir=log_dir)
    logger.emit(_make_event())

    assert _today_file(log_dir).exists()


def test_persistent_emit_writes_valid_json(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "test_logs")
    logger = PersistentEventLogger(log_dir=log_dir)
    event = _make_event(turn_id="alpha")
    logger.emit(event)

    payload = _today_file(log_dir).read_text(encoding="utf-8").strip()
    loaded = json.loads(payload)
    assert loaded["turn_id"] == "alpha"
    assert loaded["event_type"] == event.event_type
    assert loaded["lane_decision"] == event.lane_decision
    assert loaded["resolved_by"] == event.resolved_by


def test_persistent_multiple_events(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "test_logs")
    logger = PersistentEventLogger(log_dir=log_dir)
    logger.emit(_make_event(turn_id="one"))
    logger.emit(_make_event(turn_id="two"))
    logger.emit(_make_event(turn_id="three"))

    lines = _today_file(log_dir).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)


def test_persistent_preserves_in_memory(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "test_logs")
    logger = PersistentEventLogger(log_dir=log_dir)
    event_a = _make_event(turn_id="a")
    event_b = _make_event(turn_id="b")
    logger.emit(event_a)
    logger.emit(event_b)

    exported = logger.export()
    assert exported == [asdict(event_a), asdict(event_b)]


def test_read_log_returns_events(tmp_path: Path) -> None:
    log_dir = str(tmp_path / "test_logs")
    logger = PersistentEventLogger(log_dir=log_dir)
    event_a = _make_event(turn_id="a")
    event_b = _make_event(turn_id="b")
    logger.emit(event_a)
    logger.emit(event_b)

    loaded = logger.read_log()
    assert loaded == [asdict(event_a), asdict(event_b)]


def test_read_log_nonexistent_date(tmp_path: Path) -> None:
    logger = PersistentEventLogger(log_dir=str(tmp_path / "test_logs"))
    assert logger.read_log("1999-01-01") == []


def test_log_dir_created_automatically(tmp_path: Path) -> None:
    missing_dir = tmp_path / "deep" / "nested" / "logs"
    assert not missing_dir.exists()
    PersistentEventLogger(log_dir=str(missing_dir))
    assert missing_dir.exists()

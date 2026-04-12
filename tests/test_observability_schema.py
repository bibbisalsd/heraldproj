from __future__ import annotations
from jarvis.observability.events import EventLogger, EventRecord


def test_observability_event_contains_required_fields():
    logger = EventLogger()
    record = EventRecord.build(
        event_type="turn_complete",
        turn_id="t1",
        lane_decision="realtime",
        resolved_by="tool_only",
        elapsed_ms=120,
        addon_id=None,
        channel_id=None,
    )
    logger.emit(record)
    event = logger.export()[0]
    required = {
        "event_type",
        "turn_id",
        "lane_decision",
        "resolved_by",
        "elapsed_ms",
        "timestamp",
        "addon_id",
        "channel_id",
        "error_rate_window_50",
        "degraded_mode_active",
        "crsis_status",
        "crsis_findings",
        "crsis_snapshot_jsonl",
        "crsis_snapshot_latest",
    }
    assert required <= set(event.keys())

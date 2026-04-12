from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from jarvis.utils.time_utils import utc_now_iso


@dataclass
class EventRecord:
    event_type: str
    turn_id: str
    lane_decision: str
    resolved_by: str
    elapsed_ms: int
    timestamp: str
    addon_id: str | None = None
    channel_id: str | None = None
    error_rate_window_50: float = 0.0
    degraded_mode_active: bool = False
    crsis_status: str | None = None
    crsis_findings: int = 0
    crsis_snapshot_jsonl: str | None = None
    crsis_snapshot_latest: str | None = None
    crsis_reason: str | None = None
    turn_artifact: dict | None = None
    payload: dict | None = None

    @staticmethod
    def build(
        event_type: str,
        turn_id: str,
        lane_decision: str,
        resolved_by: str,
        elapsed_ms: int,
        addon_id: str | None = None,
        channel_id: str | None = None,
        degraded_mode_active: bool = False,
        crsis_status: str | None = None,
        crsis_reason: str | None = None,
        crsis_findings: int = 0,
        crsis_snapshot_jsonl: str | None = None,
        crsis_snapshot_latest: str | None = None,
        turn_artifact: dict | None = None,
        payload: dict | None = None,
    ) -> "EventRecord":
        return EventRecord(
            event_type=event_type,
            turn_id=turn_id,
            lane_decision=lane_decision,
            resolved_by=resolved_by,
            elapsed_ms=elapsed_ms,
            timestamp=utc_now_iso(),
            addon_id=addon_id,
            channel_id=channel_id,
            degraded_mode_active=degraded_mode_active,
            crsis_status=crsis_status,
            crsis_reason=crsis_reason,
            crsis_findings=crsis_findings,
            crsis_snapshot_jsonl=crsis_snapshot_jsonl,
            crsis_snapshot_latest=crsis_snapshot_latest,
            turn_artifact=turn_artifact,
            payload=payload,
        )


class EventLogger:
    def __init__(self) -> None:
        self._events: List[EventRecord] = []

    def emit(self, record: EventRecord) -> None:
        self._events.append(record)

    def export(self) -> List[Dict[str, object]]:
        return [asdict(event) for event in self._events]


class PersistentEventLogger(EventLogger):
    """Event logger that also persists events to daily JSONL files."""

    def __init__(self, log_dir: str = "./logs") -> None:
        super().__init__()
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, record: EventRecord) -> None:
        super().emit(record)
        self._write_jsonl(record)

    def _write_jsonl(self, record: EventRecord) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = self._log_dir / f"jarvis_events_{today}.jsonl"
        line = json.dumps(asdict(record), default=str)
        with filepath.open("a", encoding="utf-8") as file_obj:
            file_obj.write(line + "\n")

    def read_log(self, date_str: str | None = None) -> list[dict]:
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = self._log_dir / f"jarvis_events_{date_str}.jsonl"
        if not filepath.exists():
            return []
        events: list[dict] = []
        with filepath.open("r", encoding="utf-8") as file_obj:
            for line in file_obj:
                payload = line.strip()
                if payload:
                    events.append(json.loads(payload))
        return events

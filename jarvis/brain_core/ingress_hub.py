from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .contracts import RawEvent


class IngressHub:
    def __init__(self) -> None:
        self._events: list[RawEvent] = []

    def accept_raw_event(self, raw_event: RawEvent) -> dict[str, Any]:
        self._events.append(raw_event)
        return {"ok": True, "event": asdict(raw_event)}

    @property
    def events(self) -> list[RawEvent]:
        return list(self._events)

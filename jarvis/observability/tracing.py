from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
import re


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


TRACE_LEVEL_ORDER = {
    "basic": 0,
    "verbose": 1,
    "trace": 2,
}

_CREATOR_PHRASE_PATTERNS = (
    re.compile(r"\bfive\s+zero\s+six\s+eight\b", re.IGNORECASE),
    re.compile(r"\b5\s+0\s+6\s+8\b", re.IGNORECASE),
    re.compile(r"\b5068\b"),
    re.compile(r"\btwo\s+fifty\s+nine\b", re.IGNORECASE),
    re.compile(r"\b2\s+50\s+9\b"),
    re.compile(r"\b259\b"),
)


@dataclass(frozen=True)
class TraceRecord:
    turn_id: str
    event: str
    timestamp: str
    level: str = "basic"
    category: str = "runtime"
    detail: dict[str, Any] = field(default_factory=dict)


class Tracer:
    def __init__(self, level: str = "basic") -> None:
        self.level = level if level in TRACE_LEVEL_ORDER else "basic"
        self.records: list[TraceRecord] = []

    def emit(
        self,
        turn_id: str,
        event: str,
        detail: Mapping[str, Any] | str | None = None,
        *,
        level: str = "basic",
        category: str = "runtime",
        sensitive: bool = False,
    ) -> None:
        normalized_level = level if level in TRACE_LEVEL_ORDER else "basic"
        if TRACE_LEVEL_ORDER[normalized_level] > TRACE_LEVEL_ORDER[self.level]:
            return

        payload = self._normalize_detail(detail, sensitive=sensitive)
        self.records.append(
            TraceRecord(
                turn_id=turn_id,
                event=event,
                timestamp=_utc(),
                level=normalized_level,
                category=category,
                detail=payload,
            )
        )

    def export(
        self,
        *,
        turn_id: str | None = None,
        minimum_level: str = "basic",
    ) -> list[dict[str, Any]]:
        threshold = minimum_level if minimum_level in TRACE_LEVEL_ORDER else "basic"
        exported: list[dict[str, Any]] = []
        for record in self.records:
            if turn_id is not None and record.turn_id != turn_id:
                continue
            if TRACE_LEVEL_ORDER[record.level] < TRACE_LEVEL_ORDER[threshold]:
                continue
            exported.append(asdict(record))
        return exported

    def _normalize_detail(
        self, detail: Mapping[str, Any] | str | None, *, sensitive: bool
    ) -> dict[str, Any]:
        if detail is None:
            return {}
        if isinstance(detail, str):
            return {"message": self._sanitize_value(detail, sensitive=sensitive)}
        if isinstance(detail, Mapping):
            return {
                str(key): self._sanitize_value(value, sensitive=sensitive)
                for key, value in detail.items()
            }
        return {"value": self._sanitize_value(detail, sensitive=sensitive)}

    def _sanitize_value(self, value: Any, *, sensitive: bool) -> Any:
        if isinstance(value, str):
            return (
                "<redacted:sensitive_input>" if sensitive else self._redact_text(value)
            )
        if isinstance(value, Mapping):
            return {
                str(key): self._sanitize_value(inner, sensitive=sensitive)
                for key, inner in value.items()
            }
        if isinstance(value, list):
            return [self._sanitize_value(item, sensitive=sensitive) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize_value(item, sensitive=sensitive) for item in value]
        return value

    def _redact_text(self, text: str) -> str:
        redacted = text
        for pattern in _CREATOR_PHRASE_PATTERNS:
            redacted = pattern.sub("<redacted:creator_phrase>", redacted)
        return redacted

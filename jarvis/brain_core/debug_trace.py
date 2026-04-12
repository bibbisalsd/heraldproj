"""Debug trace logging for Jarvis turns.

Provides structured JSONL logging for observability and CRSIS analysis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TraceRecord:
    """A single trace record for a turn stage."""

    turn_id: str
    timestamp: str
    stage: str
    event_type: str
    data: dict[str, Any]
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class DebugLevel:
    """Debug logging levels."""

    BASIC = "basic"  # Only turn start/end, errors, violations
    VERBOSE = "verbose"  # + stage events, memory, tool execution
    TRACE = "trace"  # + raw data, full payloads, route candidates

    # Level ordering for filtering
    _ORDER = {"basic": 0, "verbose": 1, "trace": 2}

    @classmethod
    def allows(cls, configured: str, event_level: str) -> bool:
        """Check if configured level allows an event of the given level."""
        return cls._ORDER.get(configured, 1) >= cls._ORDER.get(event_level, 1)


# Events and their minimum required level
_EVENT_LEVELS: dict[str, str] = {
    # Basic level events (always logged)
    "start": "basic",
    "rendered": "basic",
    "error": "basic",
    "latency_violation": "basic",
    "turn_complete": "basic",
    # Verbose level events
    "raw_input": "verbose",
    "reference_resolution": "verbose",
    "retrieval": "verbose",
    "route_decision": "verbose",
    "tool_execution": "verbose",
    "evidence_compiled": "verbose",
    # Phase 7: Expanded event categories for full observability
    "tts_start": "verbose",
    "tts_complete": "verbose",
    "tts_error": "verbose",
    "stt_transcript": "verbose",
    "stt_confidence": "verbose",
    "wake_word_detected": "verbose",
    "wake_word_rejected": "verbose",
    "context_resolved": "verbose",
    "memory_read": "verbose",
    "bg1_started": "verbose",
    "bg1_progress": "verbose",
    "bg1_completed": "verbose",
    "bg1_failed": "verbose",
    "gate_check": "verbose",
    "admission_result": "verbose",
    # Trace level events (everything)
    "route_candidates": "trace",
    "cache_check": "trace",
    "raw_payload": "trace",
    "memory_write": "trace",
    # Phase 7: Additional trace-level events
    "tts_audio_chunk": "trace",
    "stt_raw_audio": "trace",
    "context_packet_full": "trace",
    "evidence_packet_full": "trace",
    "route_cache_hit": "trace",
    "route_cache_miss": "trace",
    # Phase 0: Timing and error observability events
    "stage_complete": "verbose",
    "search_failed": "basic",
}


class DebugTraceLogger:
    """Structured debug trace logger for Jarvis turns."""

    def __init__(
        self,
        log_dir: str = "./logs",
        level: str = DebugLevel.VERBOSE,
        hide_sensitive: bool = True,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.level = level
        self.hide_sensitive = hide_sensitive
        self._current_turn_id: str | None = None
        self._turn_records: list[TraceRecord] = []

    def start_turn(self, turn_id: str) -> None:
        """Start a new turn trace."""
        self._current_turn_id = turn_id
        self._turn_records = []
        self._log_record(turn_id, "turn", "start", {"turn_id": turn_id})

    def _log_record(
        self,
        turn_id: str,
        stage: str,
        event_type: str,
        data: dict[str, Any],
        latency_ms: float = 0.0,
    ) -> None:
        """Log a trace record."""
        if self.hide_sensitive:
            data = self._redact_sensitive(data)

        record = TraceRecord(
            turn_id=turn_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=stage,
            event_type=event_type,
            data=data,
            latency_ms=latency_ms,
        )
        self._turn_records.append(record)

    def _redact_sensitive(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive data from trace."""
        sensitive_keys = {"creator_phrase", "password", "secret", "token", "api_key"}
        result = {}
        for key, value in data.items():
            if key.lower() in sensitive_keys:
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = self._redact_sensitive(value)
            else:
                result[key] = value
        return result

    def log_ingress(self, raw_text: str, source: str) -> None:
        """Log ingress stage."""
        if self._current_turn_id:
            self._log_record(
                self._current_turn_id,
                "ingress",
                "raw_input",
                {"raw_text": raw_text[:200], "source": source},
            )

    def log(
        self,
        stage: str,
        event_type: str,
        data: dict[str, Any],
        latency_ms: float = 0.0,
    ) -> None:
        """Log a general stage event (respects level filtering)."""
        if not self._current_turn_id:
            return
        event_level = _EVENT_LEVELS.get(event_type, "verbose")
        if not DebugLevel.allows(self.level, event_level):
            return
        self._log_record(self._current_turn_id, stage, event_type, data, latency_ms)

    def log_latency_violation(
        self,
        stage: str,
        actual_ms: float,
        budget_ms: float,
        severity: str,
        turn_id: str = "",
    ) -> None:
        """Log a latency budget violation (always logged at basic level)."""
        tid = turn_id or self._current_turn_id or "unknown"
        self._log_record(
            tid,
            stage,
            "latency_violation",
            {
                "actual_ms": round(actual_ms, 1),
                "budget_ms": round(budget_ms, 1),
                "severity": severity,
                "over_by_ms": round(actual_ms - budget_ms, 1),
            },
            actual_ms,
        )

    def log_route_decision(
        self,
        selected_intent: str,
        selected_lane: str,
        selected_source: str,
        confidence: float,
        candidates_count: int,
        cache_hit: bool = False,
    ) -> None:
        """Log route decision (verbose level)."""
        if not self._current_turn_id:
            return
        if not DebugLevel.allows(self.level, "verbose"):
            return
        self._log_record(
            self._current_turn_id,
            "route",
            "route_decision",
            {
                "intent": selected_intent,
                "lane": selected_lane,
                "source": selected_source,
                "confidence": round(confidence, 3),
                "candidates_count": candidates_count,
                "cache_hit": cache_hit,
            },
        )

    def log_route_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> None:
        """Log all route candidates (trace level only)."""
        if not self._current_turn_id:
            return
        if not DebugLevel.allows(self.level, "trace"):
            return
        self._log_record(
            self._current_turn_id,
            "route",
            "route_candidates",
            {"candidates": candidates},
        )

    def log_tool_execution(
        self,
        tool_name: str,
        ok: bool,
        elapsed_ms: float,
        lane: str = "realtime",
    ) -> None:
        """Log tool execution result (verbose level)."""
        if not self._current_turn_id:
            return
        if not DebugLevel.allows(self.level, "verbose"):
            return
        self._log_record(
            self._current_turn_id,
            "tool",
            "tool_execution",
            {
                "tool_name": tool_name,
                "ok": ok,
                "lane": lane,
            },
            elapsed_ms,
        )

    def log_resolve(
        self,
        original: str,
        rewritten: str,
        resolutions: list[dict[str, Any]],
        reason: str,
    ) -> None:
        """Log reference resolution."""
        if self._current_turn_id:
            self._log_record(
                self._current_turn_id,
                "resolve",
                "reference_resolution",
                {
                    "original": original,
                    "rewritten": rewritten,
                    "resolutions": resolutions,
                    "reason": reason,
                },
            )

    def log_memory(
        self,
        hits: list[dict[str, Any]],
        hit_count: int,
        retrieval_ms: float,
    ) -> None:
        """Log memory retrieval."""
        if self._current_turn_id:
            self._log_record(
                self._current_turn_id,
                "memory",
                "retrieval",
                {"hits": hits[:10], "hit_count": hit_count},
                retrieval_ms,
            )

    def log_output(
        self,
        spoken_text: str | None,
        display_text: str | None,
        resolved_by: str,
        total_ms: float,
    ) -> None:
        """Log output stage."""
        if self._current_turn_id:
            self._log_record(
                self._current_turn_id,
                "output",
                "rendered",
                {
                    "spoken_text": spoken_text[:200] if spoken_text else None,
                    "display_text": display_text[:200] if display_text else None,
                    "resolved_by": resolved_by,
                },
                total_ms,
            )

    def flush(self) -> str:
        """Flush trace records to JSONL file."""
        if not self._turn_records:
            return ""

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        jsonl_path = self.log_dir / f"jarvis_trace_{day}.jsonl"

        with jsonl_path.open("a", encoding="utf-8") as f:
            for record in self._turn_records:
                f.write(
                    json.dumps(asdict(record), ensure_ascii=True, default=str) + "\n"
                )

        # Also write latest turn to separate file
        latest_path = self.log_dir / "jarvis_trace_latest.json"
        with latest_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "turn_id": self._current_turn_id,
                    "records": [asdict(r) for r in self._turn_records],
                },
                f,
                ensure_ascii=True,
                indent=2,
                default=str,
            )

        self._turn_records = []
        return str(jsonl_path)


# Module-level convenience functions
_default_logger: DebugTraceLogger | None = None


def get_logger(
    log_dir: str = "./logs",
    level: str = DebugLevel.VERBOSE,
    hide_sensitive: bool = True,
) -> DebugTraceLogger:
    """Get or create the default debug trace logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = DebugTraceLogger(
            log_dir=log_dir, level=level, hide_sensitive=hide_sensitive
        )
    return _default_logger


def log_turn_start(turn_id: str) -> None:
    """Log turn start."""
    get_logger().start_turn(turn_id)


def log_turn_end(
    spoken_text: str | None,
    display_text: str | None,
    resolved_by: str,
    total_ms: float,
) -> None:
    """Log turn end and flush."""
    logger = get_logger()
    logger.log_output(spoken_text, display_text, resolved_by, total_ms)
    logger.flush()


def log_turn_summary(turn_id: str, total_ms: float, resolved_by: str) -> None:
    """Log a simple turn summary."""
    logger = get_logger()
    logger.start_turn(turn_id)
    logger.log("summary", "turn_complete", {"resolved_by": resolved_by}, total_ms)
    logger.flush()

from __future__ import annotations
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.main import JarvisRuntime

from jarvis.tools import job_status_tool
from jarvis.name_profile import normalize_title_preference


class HealthMonitor:
    """Monitors system health and provides diagnostic snapshots."""

    def __init__(self, runtime: JarvisRuntime):
        self.runtime = runtime
        self.recent_turn_latency_ms: deque[float] = deque(maxlen=16)
        self.recent_renderer_fallbacks: deque[bool] = deque(maxlen=16)
        self.recent_voice_events: deque[dict[str, object]] = deque(maxlen=16)

    def record_voice_observation(
        self,
        *,
        audio_capture_ok: bool | None,
        transcribe_ok: bool | None,
        fallback_reason: str = "",
    ) -> None:
        self.recent_voice_events.append(
            {
                "audio_capture_ok": audio_capture_ok,
                "transcribe_ok": transcribe_ok,
                "fallback_reason": str(fallback_reason or ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def runtime_health_snapshot(self) -> dict[str, object]:
        latencies = list(self.recent_turn_latency_ms)
        avg_latency_ms = (sum(latencies) / len(latencies)) if latencies else 0.0
        renderer_fallbacks = sum(1 for used in self.recent_renderer_fallbacks if used)
        voice_failures = [
            event
            for event in self.recent_voice_events
            if not event.get("transcribe_ok", True) or event.get("fallback_reason")
        ]
        missed_voice_turns = sum(
            1
            for event in voice_failures
            if event.get("fallback_reason") in {"repeat_prompt", "mic_unavailable"}
        )
        current = job_status_tool.status(self.runtime.job_status)

        findings: list[str] = []
        status = "good"
        if self.runtime.state.degraded_mode:
            status = "major_issue"
            findings.append("degraded mode is active")
        if avg_latency_ms >= 4200:
            status = "major_issue"
            findings.append("responses are much slower than usual")
        elif avg_latency_ms >= 2200:
            if status != "major_issue":
                status = "minor_issue"
            findings.append("responses are a little slower than usual")
        if missed_voice_turns >= 2:
            if status == "good":
                status = "minor_issue"
            findings.append("speech recognition has missed a few recent turns")
        if renderer_fallbacks >= 2:
            if status == "good":
                status = "minor_issue"
            findings.append(
                "the realtime composer has fallen back to deterministic replies"
            )
        if current.get("state") != "IDLE":
            findings.append(f"heavy task {current.get('job_id', 'unknown')} is active")
        if not getattr(self.runtime, "_renderer_model_preloaded", True):
            findings.append("the realtime one billion model is not preloaded")

        title_slot = self.runtime.memory.pockets.get_slot(
            "person:owner", "title_preference"
        )
        given_name_slot = self.runtime.memory.pockets.get_slot(
            "person:owner", "given_name"
        )
        title = (
            normalize_title_preference(title_slot.slot_value)
            if title_slot is not None
            else None
        )
        given_name = (
            str(given_name_slot.slot_value).strip()
            if given_name_slot is not None
            else ""
        )
        suffix = f", {title}" if title else (f", {given_name}" if given_name else "")

        if status == "good":
            canonical = f"I am good{suffix}. I am online and responding normally."
        elif status == "minor_issue":
            canonical = f"I am online{suffix}, but {findings[0]}."
        else:
            canonical = f"I am online{suffix}, but {findings[0]}."

        cache_stats = (
            self.runtime._get_cache_stats()
            if hasattr(self.runtime, "_get_cache_stats")
            else {}
        )
        latency_health = (
            self.runtime._get_latency_health()
            if hasattr(self.runtime, "_get_latency_health")
            else {}
        )

        return {
            "status": status,
            "avg_latency_ms": round(avg_latency_ms, 1),
            "last_turn_latency_ms": round(
                getattr(self.runtime, "_last_turn_latency_ms", 0.0), 1
            ),
            "voice_failure_count": len(voice_failures),
            "renderer_fallback_count": renderer_fallbacks,
            "facts": [
                f"average turn latency is {round(avg_latency_ms)} milliseconds",
                f"last turn latency was {round(getattr(self.runtime, '_last_turn_latency_ms', 0.0))} milliseconds",
                f"renderer fallback count is {renderer_fallbacks}",
                f"voice failure count is {len(voice_failures)}",
                *findings,
            ],
            "canonical_reply": canonical,
            "route_stats": self.runtime.route_trace_logger.get_route_stats()
            if hasattr(self.runtime, "route_trace_logger")
            else {},
            "cache_stats": cache_stats,
            "latency_health": latency_health,
        }

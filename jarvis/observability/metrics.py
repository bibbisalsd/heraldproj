from __future__ import annotations

from collections import deque


class MetricsWindow:
    def __init__(self, size: int = 50) -> None:
        self.size = size
        self._success = deque(maxlen=size)

    def record(self, ok: bool) -> None:
        self._success.append(1 if ok else 0)

    def error_rate(self) -> float:
        if not self._success:
            return 0.0
        failures = len(self._success) - sum(self._success)
        return failures / len(self._success)


class ToolFirstBudget:
    def __init__(self) -> None:
        self.total = 0
        self.tool_first = 0

    def record(self, resolved_by: str) -> None:
        self.total += 1
        if resolved_by in {"template", "tool_only", "tool_plus_renderer"}:
            self.tool_first += 1

    def ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return self.tool_first / self.total


class VoicePathMetrics:
    """Lightweight counters for local voice pipeline health."""

    def __init__(self) -> None:
        self.capture_attempts = 0
        self.capture_success = 0
        self.capture_failures = 0

        self.transcribe_attempts = 0
        self.transcribe_success = 0
        self.transcribe_failures = 0

        self.turns_processed = 0
        self.fallback_repeat_prompt = 0
        self.fallback_mic_unavailable = 0
        self.tts_backend_counts: dict[str, int] = {}
        self.tts_state_counts: dict[str, int] = {}
        self.tts_retry_count = 0
        self.tts_backend_fallbacks = 0
        self.voice_delivery_failures = 0
        self.voice_sink_fallback_to_text = 0
        self.reset_latest_path()

    def reset_latest_path(self) -> None:
        self.requested_input_device: str | int | None = None
        self.requested_output_device: str | int | None = None
        self.selected_input_device: dict[str, object] | None = None
        self.selected_output_device: dict[str, object] | None = None
        self.sample_rate: int | None = None
        self.capture_duration_seconds: float | None = None
        self.audio_capture_ok: bool | None = None
        self.transcribe_ok: bool | None = None
        self.fallback_reason = ""
        self.tts_backend = ""
        self.tts_state = ""
        self.tts_error = ""
        self.tts_delivery_ok: bool | None = None
        self.tts_fallback_used: bool | None = None
        self.tts_attempted_backends: list[str] = []
        self.tts_state_history: list[str] = []
        self.requested_sink: str | None = None
        self.sink_used: str | None = None
        self.delivery_detail = ""

    def record_requested_devices(
        self,
        *,
        input_device: str | int | None = None,
        output_device: str | int | None = None,
    ) -> None:
        self.requested_input_device = input_device
        self.requested_output_device = output_device

    def record_selected_devices(
        self,
        *,
        input_device: dict[str, object] | None = None,
        output_device: dict[str, object] | None = None,
    ) -> None:
        self.selected_input_device = dict(input_device) if input_device else None
        self.selected_output_device = dict(output_device) if output_device else None

    def record_capture_settings(
        self,
        *,
        sample_rate: int | None = None,
        capture_duration_seconds: float | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.capture_duration_seconds = capture_duration_seconds

    def record_capture(self, ok: bool) -> None:
        self.capture_attempts += 1
        self.audio_capture_ok = ok
        if ok:
            self.capture_success += 1
        else:
            self.capture_failures += 1

    def record_transcribe(self, ok: bool) -> None:
        self.transcribe_attempts += 1
        self.transcribe_ok = ok
        if ok:
            self.transcribe_success += 1
        else:
            self.transcribe_failures += 1

    def set_audio_capture_status(self, ok: bool | None) -> None:
        self.audio_capture_ok = ok

    def set_transcribe_status(self, ok: bool | None) -> None:
        self.transcribe_ok = ok

    def record_turn(self) -> None:
        self.turns_processed += 1

    def record_fallback(self, reason: str) -> None:
        self.fallback_reason = reason
        if reason == "repeat_prompt":
            self.fallback_repeat_prompt += 1
        elif reason == "mic_unavailable":
            self.fallback_mic_unavailable += 1

    def clear_fallback(self) -> None:
        self.fallback_reason = ""

    def record_tts_backend(self, backend: str) -> None:
        key = backend.strip().lower() or "unknown"
        self.tts_backend_counts[key] = self.tts_backend_counts.get(key, 0) + 1
        self.tts_backend = key

    def record_tts_delivery(
        self,
        *,
        backend: str,
        state: str,
        error: str = "",
        delivery_ok: bool | None = None,
        backend_fallback_used: bool = False,
        attempted_backends: list[str] | None = None,
        state_history: list[str] | None = None,
        requested_sink: str | None = None,
        sink_used: str | None = None,
        delivery_detail: str = "",
        sink_fallback_used: bool = False,
    ) -> None:
        normalized_backend = str(backend or "").strip().lower() or "unknown"
        normalized_state = str(state or "").strip().lower() or "unknown"
        normalized_error = str(error or "").strip()
        normalized_attempted_backends = [
            str(item).strip().lower()
            for item in (attempted_backends or [])
            if str(item).strip()
        ]
        normalized_state_history = [
            str(item).strip().lower()
            for item in (state_history or [])
            if str(item).strip()
        ]

        self.record_tts_backend(normalized_backend)
        self.tts_state_counts[normalized_state] = (
            self.tts_state_counts.get(normalized_state, 0) + 1
        )
        if "retrying" in normalized_state_history:
            self.tts_retry_count += 1
        if backend_fallback_used:
            self.tts_backend_fallbacks += 1
        if delivery_ok is False:
            self.voice_delivery_failures += 1
        if sink_fallback_used and str(sink_used or "").strip().lower() in {
            "discord_text",
            "active_addon_text",
            "local_text_log",
        }:
            self.voice_sink_fallback_to_text += 1

        self.tts_backend = normalized_backend
        self.tts_state = normalized_state
        self.tts_error = normalized_error
        self.tts_delivery_ok = delivery_ok
        self.tts_fallback_used = bool(backend_fallback_used)
        self.tts_attempted_backends = normalized_attempted_backends
        self.tts_state_history = normalized_state_history
        self.requested_sink = str(requested_sink or "").strip() or None
        self.sink_used = str(sink_used or "").strip() or None
        self.delivery_detail = str(delivery_detail or "").strip()

    def snapshot(self) -> dict[str, object]:
        return {
            "capture_attempts": self.capture_attempts,
            "capture_success": self.capture_success,
            "capture_failures": self.capture_failures,
            "transcribe_attempts": self.transcribe_attempts,
            "transcribe_success": self.transcribe_success,
            "transcribe_failures": self.transcribe_failures,
            "turns_processed": self.turns_processed,
            "fallback_repeat_prompt": self.fallback_repeat_prompt,
            "fallback_mic_unavailable": self.fallback_mic_unavailable,
            "tts_backend_counts": dict(self.tts_backend_counts),
            "tts_state_counts": dict(self.tts_state_counts),
            "tts_retry_count": self.tts_retry_count,
            "tts_backend_fallbacks": self.tts_backend_fallbacks,
            "voice_delivery_failures": self.voice_delivery_failures,
            "voice_sink_fallback_to_text": self.voice_sink_fallback_to_text,
            "requested_input_device": self.requested_input_device,
            "requested_output_device": self.requested_output_device,
            "selected_input_device": dict(self.selected_input_device)
            if self.selected_input_device
            else None,
            "selected_output_device": dict(self.selected_output_device)
            if self.selected_output_device
            else None,
            "sample_rate": self.sample_rate,
            "capture_duration_seconds": self.capture_duration_seconds,
            "audio_capture_ok": self.audio_capture_ok,
            "transcribe_ok": self.transcribe_ok,
            "fallback_reason": self.fallback_reason,
            "tts_backend": self.tts_backend,
            "tts_state": self.tts_state,
            "tts_error": self.tts_error,
            "tts_delivery_ok": self.tts_delivery_ok,
            "tts_fallback_used": self.tts_fallback_used,
            "tts_attempted_backends": list(self.tts_attempted_backends),
            "tts_state_history": list(self.tts_state_history),
            "requested_sink": self.requested_sink,
            "sink_used": self.sink_used,
            "delivery_detail": self.delivery_detail,
        }

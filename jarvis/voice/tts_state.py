"""TTS State Machine: Reliable speech delivery with watchdog and fallback.

States:
  idle → preparing → speaking → idle
                   → stalled → retrying → recovered → idle
                                        → failed → idle

Features:
- Watchdog timeout detects stalled speech
- Automatic retry on silent failure (configurable max retries)
- Backend fallback (kokoro → espeak → sapi)
- Device recovery after audio failures
- Queueing and speaking telemetry
- Last-spoken confirmation
"""

from __future__ import annotations

import enum
import threading
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TTSState(str, enum.Enum):
    """TTS state machine states."""

    IDLE = "idle"
    PREPARING = "preparing"
    SPEAKING = "speaking"
    STALLED = "stalled"
    RETRYING = "retrying"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass
class TTSEvent:
    """A single TTS event for telemetry."""

    event_type: str  # state_change, speak_start, speak_end, error, retry, watchdog
    timestamp: str
    state_from: str
    state_to: str
    text_preview: str = ""
    backend: str = ""
    elapsed_ms: float = 0.0
    error: str = ""
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSConfig:
    """Configuration for TTS state machine."""

    # Watchdog
    watchdog_timeout_ms: float = 15000.0  # Max time for a single speak call
    watchdog_poll_interval_ms: float = 250.0  # How often to check for stalls

    # Retry
    max_retries: int = 2
    retry_delay_ms: float = 500.0

    # Backend fallback order
    preferred_backends: list[str] = field(
        default_factory=lambda: ["kokoro", "espeak", "sapi"]
    )

    # Device recovery
    device_recovery_enabled: bool = True
    device_recovery_delay_ms: float = 1000.0

    # Telemetry
    max_telemetry_events: int = 100


class TTSStateMachine:
    """Reliable TTS with state machine, watchdog, and fallback.

    Wraps an existing TTS instance to add reliability guarantees.
    The underlying TTS.speak() is called within the state machine's
    lifecycle, with watchdog monitoring and automatic retry/fallback.
    """

    def __init__(
        self,
        tts: Any,  # The underlying TTS instance (jarvis.voice.tts.TTS)
        config: TTSConfig | None = None,
        on_state_change: Callable[[TTSState, TTSState], None] | None = None,
    ) -> None:
        self._tts = tts
        self._config = config or TTSConfig()
        self._on_state_change = on_state_change

        # State
        self._state = TTSState.IDLE
        self._state_lock = threading.Lock()

        # Current speak context
        self._current_text: str = ""
        self._current_backend: str = ""
        self._speak_start_time: float = 0.0
        self._retry_count: int = 0

        # Confirmation
        self._last_spoken_text: str = ""
        self._last_spoken_backend: str = ""
        self._last_spoken_at: str = ""
        self._last_speak_elapsed_ms: float = 0.0

        # Telemetry
        self._events: deque[TTSEvent] = deque(maxlen=self._config.max_telemetry_events)
        self._total_speaks: int = 0
        self._total_failures: int = 0
        self._total_retries: int = 0
        self._total_recoveries: int = 0

        # Watchdog
        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_stop = threading.Event()

    # ── Public API ───────────────────────────────────────────────────

    @property
    def state(self) -> TTSState:
        """Current TTS state."""
        return self._state

    def speak(self, text: str) -> dict[str, Any]:
        """Speak text with full state machine lifecycle.

        Returns: dict with ok, text, backend, elapsed_ms, retries, state, error
        """
        spoken = str(text or "").strip()
        if not spoken:
            return {
                "ok": False,
                "text": "",
                "backend": "",
                "elapsed_ms": 0.0,
                "retries": 0,
                "state": self._state.value,
                "error": "empty_text",
            }

        self._current_text = spoken
        self._retry_count = 0
        self._total_speaks += 1

        # Transition: IDLE → PREPARING
        self._transition(TTSState.PREPARING)

        # Start watchdog
        self._start_watchdog()

        try:
            result = self._attempt_speak(spoken)
        finally:
            self._stop_watchdog()

        return result

    def get_last_spoken(self) -> dict[str, str]:
        """Get confirmation of last spoken text."""
        return {
            "text": self._last_spoken_text,
            "backend": self._last_spoken_backend,
            "timestamp": self._last_spoken_at,
            "elapsed_ms": str(self._last_speak_elapsed_ms),
        }

    def get_telemetry(self) -> dict[str, Any]:
        """Get TTS telemetry summary."""
        return {
            "state": self._state.value,
            "total_speaks": self._total_speaks,
            "total_failures": self._total_failures,
            "total_retries": self._total_retries,
            "total_recoveries": self._total_recoveries,
            "success_rate": (
                (self._total_speaks - self._total_failures) / max(1, self._total_speaks)
            ),
            "recent_events": [
                {
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "state_from": e.state_from,
                    "state_to": e.state_to,
                    "backend": e.backend,
                    "elapsed_ms": e.elapsed_ms,
                    "error": e.error,
                }
                for e in list(self._events)[-10:]
            ],
        }

    def reset(self) -> None:
        """Reset to idle state after unrecoverable failure."""
        self._stop_watchdog()
        self._transition(TTSState.IDLE)
        self._retry_count = 0

    # ── Internal ─────────────────────────────────────────────────────

    def _attempt_speak(self, text: str) -> dict[str, Any]:
        """Attempt to speak with retry and backend fallback.

        Tries each backend in preferred_backends order.
        Each backend gets max_retries attempts before moving to the next.
        """
        backends_to_try = list(self._config.preferred_backends)
        if not backends_to_try:
            backends_to_try = ["default"]

        last_error = ""
        last_backend = ""
        last_elapsed_ms = 0.0

        for backend_name in backends_to_try:
            # Reset retry count for each backend
            backend_retries = 0

            while backend_retries <= self._config.max_retries:
                # Transition: PREPARING/RETRYING → SPEAKING
                self._transition(TTSState.SPEAKING)
                self._speak_start_time = time.monotonic()

                try:
                    # Try to switch backend if the TTS supports it
                    if backend_name != "default" and hasattr(self._tts, "set_backend"):
                        try:
                            self._tts.set_backend(backend_name)
                        except Exception:
                            pass  # Fall through to speak with current backend

                    result = self._tts.speak(text)
                except Exception as exc:
                    result = {
                        "ok": "false",
                        "text": text,
                        "backend": backend_name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }

                elapsed_ms = (time.monotonic() - self._speak_start_time) * 1000
                ok = str(result.get("ok", "false")).lower() == "true"
                backend = result.get("backend", backend_name)
                error = result.get("error", "")

                self._current_backend = backend
                last_error = error
                last_backend = backend
                last_elapsed_ms = elapsed_ms

                if ok and backend != "stub":
                    # Success
                    self._last_spoken_text = text
                    self._last_spoken_backend = backend
                    self._last_spoken_at = datetime.now(timezone.utc).isoformat()
                    self._last_speak_elapsed_ms = elapsed_ms

                    if self._state == TTSState.SPEAKING:
                        self._transition(TTSState.IDLE)

                    self._log_event(
                        "speak_success",
                        TTSState.SPEAKING,
                        TTSState.IDLE,
                        text_preview=text[:80],
                        backend=backend,
                        elapsed_ms=elapsed_ms,
                    )

                    return {
                        "ok": True,
                        "text": text,
                        "backend": backend,
                        "elapsed_ms": elapsed_ms,
                        "retries": self._retry_count,
                        "state": self._state.value,
                        "error": "",
                    }

                # Failure — check if we should even bother retrying
                backend_retries += 1
                self._retry_count += 1
                self._total_retries += 1

                self._log_event(
                    "speak_failed",
                    TTSState.SPEAKING,
                    TTSState.RETRYING,
                    text_preview=text[:80],
                    backend=backend,
                    elapsed_ms=elapsed_ms,
                    error=error,
                    retry_count=self._retry_count,
                )

                # FAST FALLBACK: If the backend is missing or has an import error,
                # don't wait 1.5 seconds - move to next backend immediately.
                is_permanent_failure = any(
                    x in error.lower()
                    for x in [
                        "not_found",
                        "import_error",
                        "unavailable",
                        "no such file",
                    ]
                )

                if (
                    backend_retries <= self._config.max_retries
                    and not is_permanent_failure
                ):
                    self._transition(TTSState.RETRYING)

                    # Device recovery between retries
                    if self._config.device_recovery_enabled:
                        self._attempt_device_recovery()

                    # Delay before retry
                    time.sleep(self._config.retry_delay_ms / 1000)

                    self._transition(TTSState.PREPARING)
                else:
                    # Skip retries for this backend
                    self._transition(TTSState.RETRYING)
                    self._transition(TTSState.PREPARING)
                    break  # Move to next backend immediately

        # All backends exhausted
        self._total_failures += 1
        self._transition(TTSState.FAILED)
        self._transition(TTSState.IDLE)

        return {
            "ok": False,
            "text": text,
            "backend": last_backend,
            "elapsed_ms": last_elapsed_ms,
            "retries": self._retry_count,
            "state": self._state.value,
            "error": last_error or "all_backends_exhausted",
        }

    def _attempt_device_recovery(self) -> None:
        """Attempt to recover audio device between retries."""
        self._log_event(
            "device_recovery",
            self._state,
            self._state,
            metadata={"action": "recovery_attempt"},
        )

        # Give the audio subsystem a moment to recover
        time.sleep(self._config.device_recovery_delay_ms / 1000)

        # If the underlying TTS has a warm() method, call it
        if hasattr(self._tts, "warm"):
            try:
                self._tts.warm()
                self._total_recoveries += 1
                self._log_event(
                    "device_recovered",
                    self._state,
                    TTSState.RECOVERED,
                )
            except Exception as e:
                logger.debug(f"TTS warm() recovery failed: {e}")

    # ── State transitions ────────────────────────────────────────────

    def _transition(self, new_state: TTSState) -> None:
        """Transition to a new state with event logging."""
        with self._state_lock:
            old_state = self._state
            if old_state == new_state:
                return
            self._state = new_state

        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except Exception as e:
                logger.debug(f"TTS on_state_change callback failed: {e}")

    # ── Watchdog ──────────────────────────────────────────────────────

    def _start_watchdog(self) -> None:
        """Start the watchdog thread to detect stalled speech."""
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="tts-watchdog",
        )
        self._watchdog_thread.start()

    def _stop_watchdog(self) -> None:
        """Stop the watchdog thread."""
        self._watchdog_stop.set()
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)
        self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        """Watchdog loop that detects stalled speech."""
        while not self._watchdog_stop.is_set():
            self._watchdog_stop.wait(self._config.watchdog_poll_interval_ms / 1000)

            if self._state == TTSState.SPEAKING and self._speak_start_time > 0:
                elapsed = (time.monotonic() - self._speak_start_time) * 1000
                if elapsed > self._config.watchdog_timeout_ms:
                    self._log_event(
                        "watchdog_timeout",
                        TTSState.SPEAKING,
                        TTSState.STALLED,
                        elapsed_ms=elapsed,
                        error=f"speak_stalled_after_{elapsed:.0f}ms",
                    )
                    self._transition(TTSState.STALLED)
                    break  # Let the retry logic handle it

    # ── Telemetry ────────────────────────────────────────────────────

    def _log_event(
        self,
        event_type: str,
        state_from: TTSState,
        state_to: TTSState,
        text_preview: str = "",
        backend: str = "",
        elapsed_ms: float = 0.0,
        error: str = "",
        retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a TTS event for telemetry."""
        self._events.append(
            TTSEvent(
                event_type=event_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                state_from=state_from.value,
                state_to=state_to.value,
                text_preview=text_preview,
                backend=backend,
                elapsed_ms=elapsed_ms,
                error=error,
                retry_count=retry_count,
                metadata=metadata or {},
            )
        )

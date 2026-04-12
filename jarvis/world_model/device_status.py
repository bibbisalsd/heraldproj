"""DeviceStatus - Track mic, speaker, screen, and network state."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


DeviceNetworkState = Literal["connected", "disconnected", "degraded", "unknown"]


@dataclass(frozen=True)
class DeviceStatus:
    """Device status for mic, speaker, screen, and network state."""

    mic_active: bool = False
    speaker_active: bool = False
    screen_active: bool = False
    network_state: DeviceNetworkState = "unknown"
    network_latency_ms: float | None = None
    last_checked: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def with_mic(self, active: bool) -> "DeviceStatus":
        """Create a new DeviceStatus with updated mic state."""
        return DeviceStatus(
            mic_active=active,
            speaker_active=self.speaker_active,
            screen_active=self.screen_active,
            network_state=self.network_state,
            network_latency_ms=self.network_latency_ms,
            last_checked=datetime.now(timezone.utc).isoformat(),
        )

    def with_speaker(self, active: bool) -> "DeviceStatus":
        """Create a new DeviceStatus with updated speaker state."""
        return DeviceStatus(
            mic_active=self.mic_active,
            speaker_active=active,
            screen_active=self.screen_active,
            network_state=self.network_state,
            network_latency_ms=self.network_latency_ms,
            last_checked=datetime.now(timezone.utc).isoformat(),
        )

    def with_screen(self, active: bool) -> "DeviceStatus":
        """Create a new DeviceStatus with updated screen state."""
        return DeviceStatus(
            mic_active=self.mic_active,
            speaker_active=self.speaker_active,
            screen_active=active,
            network_state=self.network_state,
            network_latency_ms=self.network_latency_ms,
            last_checked=datetime.now(timezone.utc).isoformat(),
        )

    def with_network(
        self, state: DeviceNetworkState, latency_ms: float | None = None
    ) -> "DeviceStatus":
        """Create a new DeviceStatus with updated network state."""
        valid_states = {"connected", "disconnected", "degraded", "unknown"}
        if state not in valid_states:
            raise ValueError(
                f"Invalid network state: {state}. Must be one of {valid_states}"
            )
        return DeviceStatus(
            mic_active=self.mic_active,
            speaker_active=self.speaker_active,
            screen_active=self.screen_active,
            network_state=state,
            network_latency_ms=latency_ms,
            last_checked=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def all_inactive() -> "DeviceStatus":
        """Create a DeviceStatus with all devices inactive."""
        return DeviceStatus(
            mic_active=False,
            speaker_active=False,
            screen_active=False,
            network_state="unknown",
        )

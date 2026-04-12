from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .contracts import RawEvent


@dataclass
class AddonAudioChannel:
    channel_id: str
    addon_id: str
    enabled: bool = True
    listening: bool = True
    wake_required: bool = True
    vad_enabled: bool = True


@dataclass
class AddonTextChannel:
    """Text channel for addon ingress/egress.

    Phase 4C: Ingress & Delivery
    """

    channel_id: str
    addon_id: str
    enabled: bool = True
    ingress_enabled: bool = True
    egress_enabled: bool = True
    loop_prevention: bool = True
    # Track recent messages to prevent loops
    _recent_message_ids: set[str] = field(default_factory=set)


class AddonAudioPipeline:
    """Addon audio pipeline with channel management.

    Phase 4C: Extended with text ingress/egress support
    """

    def __init__(self, emit_raw_event: Callable[[RawEvent], dict]) -> None:
        self._emit_raw_event = emit_raw_event
        self.channels: dict[str, AddonAudioChannel] = {}
        self.text_channels: dict[str, AddonTextChannel] = {}
        # Loop prevention: track recent addon-sourced messages
        self._recent_addon_messages: dict[str, str] = {}  # addon_id -> last message
        self._message_history: list = []  # (addon_id, message, turn_id)

    def register_channel(self, channel: AddonAudioChannel) -> None:
        self.channels[channel.channel_id] = channel

    def register_text_channel(self, channel: AddonTextChannel) -> None:
        self.text_channels[channel.channel_id] = channel

    def set_channel_enabled(self, channel_id: str, enabled: bool) -> bool:
        channel: Optional[AddonAudioChannel] = self.channels.get(channel_id)
        if channel is None:
            return False
        channel.enabled = enabled
        return True

    def set_text_channel_enabled(self, channel_id: str, enabled: bool) -> bool:
        channel = self.text_channels.get(channel_id)
        if channel is None:
            return False
        channel.enabled = enabled
        channel.ingress_enabled = enabled
        channel.egress_enabled = enabled
        return True

    def emit(self, channel_id: str, speaker_id: str, payload: str) -> dict[str, str]:
        channel: Optional[AddonAudioChannel] = self.channels.get(channel_id)
        if channel is None:
            return {"ok": "false", "reason": "unknown_channel"}
        if not channel.enabled or not channel.listening:
            return {"ok": "false", "reason": "channel_disabled"}

        event = RawEvent(
            source="addon",
            addon_id=channel.addon_id,
            speaker_id=speaker_id,
            channel=channel.channel_id,
            payload=payload,
        )
        self._emit_raw_event(event)
        return {"ok": "true", "reason": "emitted"}

    # =============================================================================
    # Phase 4C: Text Ingress/Egress with Loop Prevention
    # =============================================================================

    def emit_text(
        self, addon_id: str, channel_id: str, payload: str, turn_id: str
    ) -> dict[str, str]:
        """Emit text from addon through ingress hub.

        Phase 4C: Text ingress through normal ingress_hub
        Includes loop prevention for bot/self traffic.

        Args:
            addon_id: Source addon ID
            channel_id: Channel ID
            payload: Text payload
            turn_id: Current turn ID for tracking

        Returns: dict with ok, reason, and event data
        """
        channel = self.text_channels.get(channel_id)
        if channel is None:
            return {"ok": False, "reason": "unknown_channel", "channel_id": channel_id}

        if not channel.enabled or not channel.ingress_enabled:
            return {"ok": False, "reason": "channel_disabled", "channel_id": channel_id}

        # Loop prevention: check if this is a repeat of recent addon output
        if channel.loop_prevention:
            if self._is_loop(addon_id, payload):
                return {"ok": False, "reason": "loop_prevented", "loop_detected": True}

        event = RawEvent(
            source="addon_text",
            addon_id=addon_id,
            speaker_id=f"addon:{addon_id}",
            channel=channel_id,
            payload=payload,
            metadata={"turn_id": turn_id, "loop_prevention": channel.loop_prevention},
        )
        result = self._emit_raw_event(event)

        # Track for loop prevention
        self._track_message(addon_id, payload, turn_id)

        return result

    def should_deliver_to_addon(
        self, addon_id: str, channel_id: str, payload: str
    ) -> bool:
        """Check if outbound message should be delivered to addon.

        Phase 4C: Sink adapter with loop prevention
        Prevents delivering addon's own output back to itself.

        Args:
            addon_id: Target addon ID
            channel_id: Channel ID
            payload: Message payload

        Returns:
            True if message should be delivered, False if filtered
        """
        channel = self.text_channels.get(channel_id)
        if channel is None:
            return False

        if not channel.enabled or not channel.egress_enabled:
            return False

        # Loop prevention: don't deliver addon's own messages back
        if channel.loop_prevention:
            last_msg = self._recent_addon_messages.get(addon_id)
            if last_msg and payload.strip().lower() == last_msg.strip().lower():
                return False

        return True

    def deliver_to_addon(
        self, addon_id: str, channel_id: str, payload: str
    ) -> dict[str, bool]:
        """Deliver outbound message to addon sink.

        Phase 4C: Sink adapter for outbound replies

        Args:
            addon_id: Target addon ID
            channel_id: Channel ID
            payload: Message payload

        Returns: dict with delivered status and reason
        """
        if not self.should_deliver_to_addon(addon_id, channel_id, payload):
            return {"delivered": False, "reason": "filtered_by_loop_prevention"}

        # Message would be delivered to addon's input queue
        # Actual delivery mechanism depends on addon implementation
        return {"delivered": True, "addon_id": addon_id, "channel_id": channel_id}

    def _is_loop(self, addon_id: str, payload: str) -> bool:
        """Check if message is a potential loop.

        Detects:
        - Same addon sending same message twice
        - Cross-addon echo (A sends to B, B sends back to A)
        """
        # Check recent messages from this addon
        last_msg = self._recent_addon_messages.get(addon_id)
        if last_msg and payload.strip().lower() == last_msg.strip().lower():
            return True

        # Check for rapid cross-addon echo (within last 3 messages)
        for prev_addon_id, prev_payload, _ in reversed(self._message_history[-3:]):
            if (
                prev_addon_id != addon_id
                and prev_payload.strip().lower() == payload.strip().lower()
            ):
                return True

        return False

    def _track_message(self, addon_id: str, payload: str, turn_id: str) -> None:
        """Track message for loop prevention."""
        self._recent_addon_messages[addon_id] = payload
        self._message_history.append((addon_id, payload, turn_id))

        # Keep history bounded (last 20 messages)
        if len(self._message_history) > 20:
            self._message_history = self._message_history[-20:]

    def clear_loop_history(self, addon_id: Optional[str] = None) -> None:
        """Clear loop prevention history.

        Args:
            addon_id: If provided, clear only for specific addon.
                     If None, clear all history.
        """
        if addon_id:
            self._recent_addon_messages.pop(addon_id, None)
            self._message_history = [
                (aid, msg, tid)
                for aid, msg, tid in self._message_history
                if aid != addon_id
            ]
        else:
            self._recent_addon_messages.clear()
            self._message_history.clear()

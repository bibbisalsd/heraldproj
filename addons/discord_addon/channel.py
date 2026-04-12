"""Discord channel state management.

Phase 4E: Discord Completion
- Channel state for text/voice input/output
- Listening/speaking toggles
- Loop prevention
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DiscordTextChannel:
    """Discord text channel configuration."""
    channel_id: str
    enabled: bool = True
    listening: bool = True
    output_enabled: bool = True
    loop_prevention: bool = True
    _last_bot_message: Optional[str] = field(default=None, repr=False)


@dataclass
class DiscordVoiceChannel:
    """Discord voice channel configuration."""
    channel_id: str
    enabled: bool = True
    listening: bool = False  # Voice input disabled by default
    speaking: bool = False  # Voice output disabled by default
    vad_enabled: bool = True
    wake_required: bool = True


class DiscordChannelState:
    """Manage Discord channel states.

    Tracks:
    - Text channel: listening, output, loop prevention
    - Voice channel: listening (STT), speaking (TTS)
    """

    def __init__(self) -> None:
        self._text_channel: Optional[DiscordTextChannel] = None
        self._voice_channel: Optional[DiscordVoiceChannel] = None

    def set_text_channel(self, channel_id: str) -> None:
        """Configure text channel."""
        self._text_channel = DiscordTextChannel(channel_id=channel_id)

    def set_voice_channel(self, channel_id: str) -> None:
        """Configure voice channel."""
        self._voice_channel = DiscordVoiceChannel(channel_id=channel_id)

    @property
    def text_channel(self) -> Optional[DiscordTextChannel]:
        return self._text_channel

    @property
    def voice_channel(self) -> Optional[DiscordVoiceChannel]:
        return self._voice_channel

    def set_text_listening(self, listening: bool) -> bool:
        if not self._text_channel:
            return False
        self._text_channel.listening = listening
        return True

    def set_text_output(self, enabled: bool) -> bool:
        if not self._text_channel:
            return False
        self._text_channel.output_enabled = enabled
        return True

    def set_voice_listening(self, listening: bool) -> bool:
        if not self._voice_channel:
            return False
        self._voice_channel.listening = listening
        return True

    def set_voice_speaking(self, speaking: bool) -> bool:
        if not self._voice_channel:
            return False
        self._voice_channel.speaking = speaking
        return True

    def should_process_incoming(self, author_id: str, bot_user_id: Optional[str] = None) -> bool:
        """Check if incoming message should be processed.

        Phase 4E: Loop prevention
        Don't process bot's own messages.
        """
        if not self._text_channel or not self._text_channel.listening:
            return False

        # Loop prevention: ignore bot's own messages
        if bot_user_id and author_id == bot_user_id:
            return False

        return True

    def should_send_outgoing(self, content: str) -> bool:
        """Check if outgoing message should be sent to Discord.

        Phase 4E: Loop prevention
        Don't echo back messages that came from Discord.
        """
        if not self._text_channel or not self._text_channel.output_enabled:
            return False

        # Loop prevention: don't send if matches last bot message
        if self._text_channel.loop_prevention:
            if self._text_channel._last_bot_message:
                if content.strip().lower() == self._text_channel._last_bot_message.strip().lower():
                    return False

        return True

    def record_bot_message(self, content: str) -> None:
        """Record bot message for loop prevention."""
        if self._text_channel:
            self._text_channel._last_bot_message = content

    def snapshot(self) -> Dict[str, Any]:
        """Get channel state snapshot."""
        result: Dict[str, Any] = {}
        if self._text_channel:
            result["text_channel"] = {
                "channel_id": self._text_channel.channel_id,
                "enabled": self._text_channel.enabled,
                "listening": self._text_channel.listening,
                "output_enabled": self._text_channel.output_enabled,
            }
        if self._voice_channel:
            result["voice_channel"] = {
                "channel_id": self._voice_channel.channel_id,
                "enabled": self._voice_channel.enabled,
                "listening": self._voice_channel.listening,
                "speaking": self._voice_channel.speaking,
            }
        return result

"""Discord bridge for text/voice ingress and egress.

Phase 4E: Discord Completion
- Text ingress through ingress_hub
- Text egress to Discord channel
- Loop prevention for bot messages
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional


class DiscordBridge:
    """Bridge between Discord and Harold ingress/egress system.

    Handles:
    - Incoming Discord messages -> RawEvent ingress
    - Outgoing Harold responses -> Discord channel messages
    - Voice channel join/leave
    """

    def __init__(
        self,
        token: str,
        guild_id: Optional[str] = None,
        text_channel_id: Optional[str] = None,
        voice_channel_id: Optional[str] = None,
    ) -> None:
        self.token = token
        self.guild_id = guild_id
        self.text_channel_id = text_channel_id
        self.voice_channel_id = voice_channel_id

        self._client = None
        self._connected = False
        self._emit_raw_event: Optional[Callable] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def client(self):
        return self._client

    def connect(self) -> bool:
        """Connect to Discord."""
        try:
            import discord
        except ImportError:
            return False

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.voice_states = True

        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            nonlocal self
            self._connected = True

        @self._client.event
        async def on_message(message):
            await self._handle_message(message)

        # Run connect in background
        async def _connect():
            await self._client.start(self.token)

        self._loop.run_until_complete(_connect())
        return True

    def disconnect(self) -> bool:
        """Disconnect from Discord."""
        if self._client and self._connected:
            if self._loop:
                self._loop.run_until_complete(self._client.close())
            self._connected = False
        return True

    async def close(self) -> None:
        """Async close."""
        if self._client:
            await self._client.close()
        self._connected = False

    def set_ingress_handler(self, handler: Callable) -> None:
        """Set the raw event emitter callback."""
        self._emit_raw_event = handler

    async def _handle_message(self, message) -> None:
        """Handle incoming Discord message.

        Converts to RawEvent and emits through ingress hub.
        Includes loop prevention for bot's own messages.
        """
        if not self._emit_raw_event:
            return

        # Ignore bot's own messages (loop prevention)
        if message.author.bot:
            return

        # Ignore messages from other guilds/channels if configured
        if self.guild_id and str(message.guild.id) != self.guild_id:
            return
        if self.text_channel_id and str(message.channel.id) != self.text_channel_id:
            return

        from jarvis.brain_core.contracts import RawEvent

        event = RawEvent(
            source="discord",
            addon_id="discord",
            speaker_id=f"discord:{message.author.id}",
            channel="discord_text",
            payload=message.content,
            metadata={
                "author_name": message.author.name,
                "author_id": str(message.author.id),
                "channel_id": str(message.channel.id),
                "guild_id": str(message.guild.id) if message.guild else None,
            },
        )
        self._emit_raw_event(event)

    def send_message(self, content: str) -> Dict[str, Any]:
        """Send message to Discord text channel.

        Phase 4E: Text egress through Discord
        """
        if not self._client or not self._connected:
            return {"ok": False, "reason": "not_connected"}

        if not self.text_channel_id:
            return {"ok": False, "reason": "no_text_channel"}

        async def _send():
            channel = self._client.get_channel(int(self.text_channel_id))
            if channel:
                await channel.send(content)
                return {"ok": True}
            return {"ok": False, "reason": "channel_not_found"}

        if self._loop:
            return self._loop.run_until_complete(_send())
        return {"ok": False, "reason": "no_event_loop"}

    def join_voice_channel(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """Join Discord voice channel via DiscordVoiceBridge.

        Phase 4E: Discord Voice Completion.
        """
        target_channel_id = channel_id or self.voice_channel_id
        if not target_channel_id:
            return {"ok": False, "reason": "no_voice_channel"}

        try:
            from addons.discord_addon.voice_bridge import DiscordVoiceBridge

            if not hasattr(self, "_voice_bridge") or self._voice_bridge is None:
                self._voice_bridge = DiscordVoiceBridge(
                    client=self._client,
                    guild_id=self.guild_id,
                    voice_channel_id=target_channel_id,
                )

            if self._loop:
                return self._loop.run_until_complete(
                    self._voice_bridge.join_voice_channel(target_channel_id)
                )
            return {"ok": False, "reason": "no_event_loop"}
        except ImportError:
            return {"ok": False, "reason": "voice_bridge_not_available"}
        except Exception as e:
            return {"ok": False, "reason": f"voice_join_failed: {type(e).__name__}: {e}"}

    def leave_voice_channel(self) -> Dict[str, Any]:
        """Leave Discord voice channel via DiscordVoiceBridge.

        Phase 4E: Discord Voice Completion.
        """
        if not hasattr(self, "_voice_bridge") or self._voice_bridge is None:
            return {"ok": True, "reason": "not_in_voice_channel"}

        try:
            if self._loop:
                return self._loop.run_until_complete(
                    self._voice_bridge.leave_voice_channel()
                )
            return {"ok": False, "reason": "no_event_loop"}
        except Exception as e:
            return {"ok": False, "reason": f"voice_leave_failed: {type(e).__name__}: {e}"}

    def speak_in_voice(self, text: str) -> Dict[str, Any]:
        """Speak text into the active Discord voice channel.

        Phase 4E: Discord Voice Completion - TTS egress.
        """
        if not hasattr(self, "_voice_bridge") or self._voice_bridge is None:
            return {"ok": False, "reason": "not_in_voice_channel"}

        try:
            if self._loop:
                return self._loop.run_until_complete(
                    self._voice_bridge.speak(text)
                )
            return {"ok": False, "reason": "no_event_loop"}
        except Exception as e:
            return {"ok": False, "reason": f"voice_speak_failed: {type(e).__name__}: {e}"}


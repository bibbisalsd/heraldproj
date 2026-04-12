"""Discord Voice Bridge - Phase 4E: Discord Voice Completion.

Implements async Discord voice channel streaming via discord.py VoiceClient.
Connects Discord voice audio to the Jarvis TTS/STT pipeline.

Requirements:
  - discord.py[voice]  (pip install discord.py[voice])
  - PyNaCl             (pip install PyNaCl)
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class DiscordVoiceBridge:
    """Bridge between Discord voice channels and Jarvis audio pipeline.

    Handles:
    - Joining/leaving voice channels via discord.py VoiceClient
    - Streaming TTS audio output to Discord voice channel
    - Receiving voice audio from Discord (future: STT integration)
    """

    def __init__(
        self,
        client: Any,
        guild_id: Optional[str] = None,
        voice_channel_id: Optional[str] = None,
    ) -> None:
        self._client = client
        self._guild_id = guild_id
        self._voice_channel_id = voice_channel_id
        self._voice_client: Any | None = None
        self._connected = False
        self._tts_provider: Optional[Callable[[str], bytes | None]] = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._voice_client is not None and self._voice_client.is_connected()

    def set_tts_provider(self, provider: Callable[[str], bytes | None]) -> None:
        """Set the TTS provider callback.

        The provider should accept text and return raw PCM/WAV audio bytes,
        or None if TTS is unavailable.
        """
        self._tts_provider = provider

    async def join_voice_channel(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """Join a Discord voice channel.

        Args:
            channel_id: Override voice channel ID. Falls back to configured default.

        Returns:
            Dict with 'ok' status and details.
        """
        try:
            import discord
        except ImportError:
            return {"ok": False, "reason": "discord_not_installed"}

        target_id = channel_id or self._voice_channel_id
        if not target_id:
            return {"ok": False, "reason": "no_voice_channel_configured"}

        try:
            channel = self._client.get_channel(int(target_id))
            if channel is None:
                return {"ok": False, "reason": "channel_not_found", "channel_id": target_id}

            if not isinstance(channel, discord.VoiceChannel):
                return {"ok": False, "reason": "not_a_voice_channel", "channel_id": target_id}

            # Disconnect from any existing voice connection in this guild
            if self._voice_client and self._voice_client.is_connected():
                await self._voice_client.disconnect(force=True)

            self._voice_client = await channel.connect()
            self._connected = True
            logger.info("Joined Discord voice channel: %s (%s)", channel.name, target_id)

            return {
                "ok": True,
                "channel_id": target_id,
                "channel_name": channel.name,
                "guild_id": str(channel.guild.id) if channel.guild else None,
            }

        except Exception as e:
            logger.error("Failed to join voice channel %s: %s", target_id, e)
            return {"ok": False, "reason": f"join_failed: {type(e).__name__}: {e}"}

    async def leave_voice_channel(self) -> Dict[str, Any]:
        """Leave the current Discord voice channel."""
        if not self._voice_client:
            return {"ok": True, "reason": "not_in_voice_channel"}

        try:
            if self._voice_client.is_connected():
                await self._voice_client.disconnect(force=True)
            self._voice_client = None
            self._connected = False
            logger.info("Left Discord voice channel")
            return {"ok": True}
        except Exception as e:
            logger.error("Failed to leave voice channel: %s", e)
            self._voice_client = None
            self._connected = False
            return {"ok": False, "reason": f"leave_failed: {type(e).__name__}: {e}"}

    async def speak(self, text: str) -> Dict[str, Any]:
        """Speak text into the Discord voice channel via TTS.

        Converts text to audio via the configured TTS provider,
        then streams it to the active voice connection.

        Args:
            text: Text to speak.

        Returns:
            Dict with 'ok' status.
        """
        if not self.is_connected:
            return {"ok": False, "reason": "not_connected_to_voice"}

        if not self._tts_provider:
            return {"ok": False, "reason": "no_tts_provider"}

        try:
            import discord

            # Generate audio via TTS provider
            audio_data = self._tts_provider(text)
            if audio_data is None:
                return {"ok": False, "reason": "tts_generation_failed"}

            # Wrap raw audio bytes into a discord-compatible AudioSource
            audio_source = discord.FFmpegPCMAudio(
                io.BytesIO(audio_data),
                pipe=True,
            )

            # Play with a completion event
            play_complete = asyncio.Event()

            def after_play(error: Exception | None) -> None:
                if error:
                    logger.error("Discord voice playback error: %s", error)
                play_complete.set()

            self._voice_client.play(audio_source, after=after_play)

            # Wait for playback to complete (with timeout)
            try:
                await asyncio.wait_for(play_complete.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                logger.warning("Voice playback timed out after 60s")
                if self._voice_client.is_playing():
                    self._voice_client.stop()

            return {"ok": True, "text": text[:100]}

        except Exception as e:
            logger.error("Failed to speak in voice channel: %s", e)
            return {"ok": False, "reason": f"speak_failed: {type(e).__name__}: {e}"}

    def get_status(self) -> Dict[str, Any]:
        """Get current voice bridge status."""
        return {
            "connected": self.is_connected,
            "voice_channel_id": self._voice_channel_id,
            "guild_id": self._guild_id,
            "has_tts_provider": self._tts_provider is not None,
            "is_playing": (
                self._voice_client.is_playing()
                if self._voice_client and hasattr(self._voice_client, "is_playing")
                else False
            ),
        }

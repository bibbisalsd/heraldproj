"""Discord health checker.

Phase 4E: Discord Completion
- Health checks: logged in, guild reachable, websocket alive
"""
from __future__ import annotations

from typing import Any, Dict


class DiscordHealthChecker:
    """Health checker for Discord addon.

    Checks:
    - logged_in: Bot is authenticated with Discord
    - guild_reachable: Configured guild is accessible
    - websocket_alive: WebSocket connection is active
    - text_channel_ready: Text channel is available
    - voice_channel_ready: Voice channel is available
    """

    def __init__(self, bridge) -> None:
        self._bridge = bridge

    def check(self) -> Dict[str, Any]:
        """Run full health check."""
        result = {
            "ok": True,
            "logged_in": False,
            "guild_reachable": False,
            "websocket_alive": False,
            "text_channel_ready": False,
            "voice_channel_ready": False,
            "errors": [],
        }

        # Check if connected
        if not self._bridge:
            result["ok"] = False
            result["errors"].append("bridge_not_initialized")
            return result

        # Check WebSocket connection
        result["websocket_alive"] = self._bridge.is_connected

        if not result["websocket_alive"]:
            result["ok"] = False
            result["errors"].append("websocket_disconnected")
        else:
            result["logged_in"] = True

        # Check guild reachability
        if self._bridge.guild_id and self._bridge.client:
            guild = self._bridge.client.get_guild(int(self._bridge.guild_id))
            result["guild_reachable"] = guild is not None
            if not result["guild_reachable"]:
                result["errors"].append("guild_not_found")

        # Check text channel
        if self._bridge.text_channel_id and self._bridge.client:
            channel = self._bridge.client.get_channel(int(self._bridge.text_channel_id))
            result["text_channel_ready"] = channel is not None
            if not result["text_channel_ready"]:
                result["errors"].append("text_channel_not_found")

        # Check voice channel
        if self._bridge.voice_channel_id and self._bridge.client:
            channel = self._bridge.client.get_channel(int(self._bridge.voice_channel_id))
            result["voice_channel_ready"] = channel is not None
            if not result["voice_channel_ready"]:
                result["errors"].append("voice_channel_not_found")

        # Overall status
        critical_ok = result["logged_in"] and result["websocket_alive"]
        result["ok"] = critical_ok

        return result

    def quick_status(self) -> str:
        """Get quick status string."""
        result = self.check()
        if result["ok"]:
            return "healthy"
        elif result["websocket_alive"]:
            return "degraded"
        else:
            return "offline"

"""Discord addon for Harold - text/voice bridge with channel controls.

Phase 4E: Discord Completion
- Text ingress/output through ingress_hub
- Permission mapping (owner/trusted/guest)
- Health checks (logged in, guild reachable, websocket alive)
- Channel state management
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from .bridge import DiscordBridge
from .channel import DiscordChannelState
from .health import DiscordHealthChecker
from .permissions import map_identity_to_profile


# Global addon state
_bridge: Optional[DiscordBridge] = None
_channel_state: Optional[DiscordChannelState] = None
_health_checker: Optional[DiscordHealthChecker] = None
_initialized = False
_enabled = False


def initialize() -> None:
    """Initialize Discord addon on load."""
    global _bridge, _channel_state, _health_checker, _initialized

    import os
    token = os.environ.get("DISCORD_BOT_TOKEN")
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    text_channel_id = os.environ.get("DISCORD_TEXT_CHANNEL_ID")
    voice_channel_id = os.environ.get("DISCORD_VOICE_CHANNEL_ID")

    if not token:
        return

    _bridge = DiscordBridge(
        token=token,
        guild_id=guild_id,
        text_channel_id=text_channel_id,
        voice_channel_id=voice_channel_id,
    )
    _channel_state = DiscordChannelState()
    _health_checker = DiscordHealthChecker(_bridge)
    _initialized = True


def validate() -> bool:
    """Validate addon configuration before load."""
    import os
    token = os.environ.get("DISCORD_BOT_TOKEN")
    return bool(token)


def startup() -> None:
    """Enable addon - connect to Discord."""
    global _enabled, _bridge

    if not _initialized:
        initialize()

    if _bridge and _initialized:
        if _bridge.connect():
            _enabled = True


def shutdown() -> None:
    """Disable addon - disconnect from Discord."""
    global _enabled, _bridge, _channel_state, _health_checker

    if _bridge:
        _bridge.disconnect()
    _bridge = None
    _channel_state = None
    _health_checker = None
    _initialized = False
    _enabled = False


def healthcheck() -> Dict[str, Any]:
    """Run health check.

    Returns status with:
    - ok: Overall health status
    - logged_in: Bot is authenticated
    - guild_reachable: Guild is accessible
    - websocket_alive: WebSocket connection is active
    - text_channel_ready: Text channel is available
    - voice_channel_ready: Voice channel is available
    """
    global _health_checker, _bridge, _enabled

    if not _health_checker or not _bridge:
        return {"ok": False, "error": "addon_not_initialized"}

    return _health_checker.check()


def get_bridge() -> Optional[DiscordBridge]:
    """Get the Discord bridge instance."""
    return _bridge


def get_channel_state() -> Optional[DiscordChannelState]:
    """Get the channel state manager."""
    return _channel_state


def is_enabled() -> bool:
    """Check if addon is enabled."""
    return _enabled


def is_initialized() -> bool:
    """Check if addon is initialized."""
    return _initialized

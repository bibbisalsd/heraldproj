"""Discord addon command pack.

Phase 4E: Discord Completion
- Channel control commands
- Voice join/leave commands
"""
from __future__ import annotations

from typing import Any, Dict


def handle_discord_output_on() -> Dict[str, Any]:
    """Enable Discord text output."""
    from . import get_channel_state

    state = get_channel_state()
    if state and state.text_channel:
        state.set_text_output(True)
        return {"ok": True, "action": "discord_output_enabled"}
    return {"ok": False, "reason": "text_channel_not_configured"}


def handle_discord_output_off() -> Dict[str, Any]:
    """Disable Discord text output."""
    from . import get_channel_state

    state = get_channel_state()
    if state and state.text_channel:
        state.set_text_output(False)
        return {"ok": True, "action": "discord_output_disabled"}
    return {"ok": False, "reason": "text_channel_not_configured"}


def handle_discord_listen_on() -> Dict[str, Any]:
    """Enable Discord text listening."""
    from . import get_channel_state

    state = get_channel_state()
    if state and state.text_channel:
        state.set_text_listening(True)
        return {"ok": True, "action": "discord_listening_enabled"}
    return {"ok": False, "reason": "text_channel_not_configured"}


def handle_discord_listen_off() -> Dict[str, Any]:
    """Disable Discord text listening."""
    from . import get_channel_state

    state = get_channel_state()
    if state and state.text_channel:
        state.set_text_listening(False)
        return {"ok": True, "action": "discord_listening_disabled"}
    return {"ok": False, "reason": "text_channel_not_configured"}


def handle_discord_join_voice() -> Dict[str, Any]:
    """Join Discord voice channel."""
    from . import get_bridge

    bridge = get_bridge()
    if bridge:
        result = bridge.join_voice_channel()
        if result.get("ok"):
            if state := get_channel_state():
                state.set_voice_speaking(True)
        return result
    return {"ok": False, "reason": "bridge_not_initialized"}


def handle_discord_leave_voice() -> Dict[str, Any]:
    """Leave Discord voice channel."""
    from . import get_bridge, get_channel_state

    bridge = get_bridge()
    if bridge:
        result = bridge.leave_voice_channel()
        if result.get("ok"):
            if state := get_channel_state():
                state.set_voice_speaking(False)
        return result
    return {"ok": False, "reason": "bridge_not_initialized"}


def command_pack() -> list[str]:
    """Return command pack descriptions."""
    return [
        "discord output on - Enable text output to Discord",
        "discord output off - Disable text output to Discord",
        "discord listen on - Enable listening to Discord messages",
        "discord listen off - Disable listening to Discord messages",
        "discord join voice - Join voice channel",
        "discord leave voice - Leave voice channel",
    ]

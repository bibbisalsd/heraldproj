from __future__ import annotations

from jarvis.brain_core.addon_channel_state import AddonChannelState
from jarvis.brain_core.addon_manager import AddonManager


def enable_addon(manager: AddonManager, addon_id: str) -> str:
    return "enabled" if manager.start(addon_id) else "failed"


def disable_addon(manager: AddonManager, addon_id: str) -> str:
    return "disabled" if manager.stop(addon_id) else "failed"


def set_channel_listening(
    channel_state: AddonChannelState, channel_id: str, enabled: bool
) -> str:
    ok = channel_state.set_listening(channel_id, enabled)
    if not ok:
        return "missing_channel"
    return "listening_on" if enabled else "listening_off"

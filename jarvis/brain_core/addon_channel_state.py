from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AddonChannel:
    channel_id: str
    addon_id: str
    enabled: bool = True
    listening: bool = True
    wake_required: bool = True
    vad_enabled: bool = True
    output_target: str = "active_addon_text"
    speaking_mutex_group: str = "default"


class AddonChannelState:
    def __init__(self) -> None:
        self._channels: dict[str, AddonChannel] = {}

    def register(self, channel: AddonChannel) -> None:
        self._channels[channel.channel_id] = channel

    def set_enabled(self, channel_id: str, enabled: bool) -> bool:
        if channel_id not in self._channels:
            return False
        self._channels[channel_id].enabled = enabled
        return True

    def set_listening(self, channel_id: str, listening: bool) -> bool:
        if channel_id not in self._channels:
            return False
        self._channels[channel_id].listening = listening
        return True

    def snapshot(self) -> dict[str, dict]:
        return {cid: vars(state).copy() for cid, state in self._channels.items()}

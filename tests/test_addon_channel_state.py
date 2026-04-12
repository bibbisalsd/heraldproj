from __future__ import annotations
from jarvis.brain_core.addon_channel_state import AddonChannel, AddonChannelState


def test_addon_channel_state_toggle():
    state = AddonChannelState()
    state.register(AddonChannel(channel_id="c1", addon_id="discord"))
    assert state.set_enabled("c1", False) is True
    assert state.set_listening("c1", False) is True
    snap = state.snapshot()
    assert snap["c1"]["enabled"] is False
    assert snap["c1"]["listening"] is False

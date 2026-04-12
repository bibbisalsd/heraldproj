from addons.discord_addon.channel import DiscordChannelState


def test_discord_voice_channel_toggle():
    state = DiscordChannelState()
    state.set_voice_enabled(False)
    assert state.voice_enabled is False
    state.set_voice_enabled(True)
    assert state.voice_enabled is True

from addons.discord_addon.channel import DiscordChannelState


def test_discord_text_channel_toggle():
    state = DiscordChannelState()
    state.set_text_enabled(False)
    assert state.text_enabled is False
    state.set_text_enabled(True)
    assert state.text_enabled is True

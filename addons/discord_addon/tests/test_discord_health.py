from addons.discord_addon.health import healthcheck


def test_discord_healthcheck_passes_with_valid_bindings():
    result = healthcheck(guild_id="1", text_channel_id="2", voice_channel_id="3")
    assert result["ok"] is True


def test_discord_healthcheck_fails_with_missing_bindings():
    result = healthcheck(guild_id="", text_channel_id="2", voice_channel_id="")
    assert result["ok"] is False

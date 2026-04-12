from addons.discord_addon.commands import command_pack


def test_discord_command_pack_has_expected_controls():
    commands = command_pack()
    assert "discord output on" in commands
    assert "discord listen off" in commands

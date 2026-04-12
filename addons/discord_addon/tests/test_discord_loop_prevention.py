from addons.discord_addon.bridge import should_emit_to_ingress


def test_discord_loop_prevention_blocks_bot_echo():
    assert should_emit_to_ingress(author_id="bot_1", bot_id="bot_1") is False
    assert should_emit_to_ingress(author_id="user_2", bot_id="bot_1") is True

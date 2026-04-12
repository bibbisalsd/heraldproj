from addons.discord_addon.manifest import build_manifest


def test_discord_addon_manifest_loads():
    manifest = build_manifest()
    assert manifest.addon_id == "discord"
    assert manifest.safe_in_degraded_mode is True

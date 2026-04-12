from addons.discord_addon.permissions import map_identity_to_profile


def test_discord_permission_map_reuses_core_profiles():
    assert map_identity_to_profile("owner:123") == "owner"
    assert map_identity_to_profile("trusted:555") == "trusted"
    assert map_identity_to_profile("random:abc") == "guest"

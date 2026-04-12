from __future__ import annotations
from jarvis.brain_core.addon_command_registry import AddonCommandRegistry
from jarvis.brain_core.addon_permissions import AddonPermissionMapper


def test_addon_command_registry_runs_namespaced_command():
    registry = AddonCommandRegistry()
    registry.register("discord", "join voice", lambda: "joined")
    assert registry.execute("discord", "join voice") == "joined"
    assert registry.execute("discord", "missing") is None


def test_addon_permission_mapper_defaults_to_guest():
    mapper = AddonPermissionMapper()
    mapper.register_identity("trusted_user", "trusted")
    assert mapper.resolve_profile("trusted_user") == "trusted"
    assert mapper.resolve_profile("unknown") == "guest"

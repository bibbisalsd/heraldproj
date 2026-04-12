from __future__ import annotations
from jarvis.brain_core.addon_registry import AddonRegistry
from jarvis.brain_core.contracts import AddonManifest


def test_addon_registry_accepts_valid_manifest():
    registry = AddonRegistry()
    manifest = AddonManifest(
        addon_id="discord",
        addon_name="Discord Addon",
        version="0.1.0",
        capability_summary="Discord bridge",
    )
    errors = registry.register_manifest(manifest)
    assert errors == []
    assert "discord" in registry.manifests


def test_addon_registry_rejects_invalid_manifest():
    registry = AddonRegistry()
    manifest = AddonManifest(addon_id="", addon_name="Broken", version="", capability_summary="")
    errors = registry.register_manifest(manifest)
    assert "missing_addon_id" in errors
    assert "missing_version" in errors

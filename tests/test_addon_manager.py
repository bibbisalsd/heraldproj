from __future__ import annotations
from unittest.mock import patch
from jarvis.brain_core.addon_manager import AddonManager
from jarvis.brain_core.addon_registry import AddonRegistry
from jarvis.brain_core.contracts import AddonManifest

def _manifest() -> AddonManifest:
    return AddonManifest(
        addon_id="discord",
        addon_name="Discord",
        version="0.1.0",
        capability_summary="Bridge + channel controls",
    )

@patch("jarvis.brain_core.addon_manager.AddonManager._load_addon_module")
def test_addon_manager_lifecycle(mock_load):
    registry = AddonRegistry()
    manager = AddonManager(registry)
    manager.discover([_manifest()])
    mock_load.return_value = True
    assert manager.states["discord"] == "DISCOVERED"
    assert manager.load("discord") is True
    assert manager.start("discord") is True
    assert manager.stop("discord") is True
    assert manager.unload("discord") is True
    assert manager.states["discord"] == "UNLOADED"

def test_addon_manager_fault_state():
    registry = AddonRegistry()
    manager = AddonManager(registry)
    manager.discover([_manifest()])
    assert manager.fault("discord") is True
    assert manager.states["discord"] == "FAULTED"

from types import SimpleNamespace
from pathlib import Path
from jarvis.brain_core.addon_manager import AddonManager
from jarvis.brain_core.addon_registry import AddonRegistry
from jarvis.brain_core.contracts import AddonManifest

registry = AddonRegistry()
manager = AddonManager(registry)
manifest = AddonManifest(
    addon_id="discord",
    addon_name="Discord",
    version="0.1.0",
    capability_summary="Discord bridge",
)
print("Before discover:", manager.states)
manager.discover([manifest])
print("After discover:", manager.states)
manager.load("discord")
print("After load:", manager.states)
manager.start("discord")
print("After start:", manager.states)

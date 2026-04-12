from __future__ import annotations

from typing import Any, Iterable

from .addon_registry import AddonRegistry, AddonDiscoveryResult
from .contracts import AddonManifest


VALID_STATES = {"DISCOVERED", "LOADED", "ENABLED", "DISABLED", "FAULTED", "UNLOADED"}


class AddonManager:
    """Addon lifecycle manager with complete state machine.

    Phase 4B: Addon Lifecycle
    - DISCOVERED → VALIDATED → LOADED → ENABLED → DISABLED → FAULTED → UNLOADED
    - Validation hook for each addon on load
    - Health check integration
    - Fault detection and auto-fault on crash
    """

    def __init__(self, registry: AddonRegistry) -> None:
        self.registry = registry
        self.states: dict[str, str] = {}
        self._health_cache: dict[str, dict[str, Any]] = {}

    def discover_all(self) -> list[AddonDiscoveryResult]:
        """Auto-discover all addons in the registry's addons directory.

        Phase 4A: Addon Discovery
        """
        results = self.registry.discover_all()
        for result in results:
            if result.success:
                self.states[result.addon_id] = "DISCOVERED"
            else:
                self.states[result.addon_id] = "FAULTED"
        return results

    def discover(self, manifests: Iterable[AddonManifest]) -> None:
        for manifest in manifests:
            errors = self.registry.register_manifest(manifest)
            if errors:
                self.states[manifest.addon_id] = "FAULTED"
            else:
                self.states[manifest.addon_id] = "DISCOVERED"

    def enable(self, addon_id: str) -> bool:
        return self.start(addon_id)

    def disable(self, addon_id: str) -> bool:
        return self.stop(addon_id)

    def fault(self, addon_id: str) -> bool:
        if addon_id not in self.states:
            return False
        self.states[addon_id] = "FAULTED"
        return True

    def unload(self, addon_id: str) -> bool:
        if addon_id not in self.states:
            return False
        self.states[addon_id] = "UNLOADED"
        return True

    # =============================================================================
    # Phase 4B: Addon Lifecycle - Validation and Health Checks
    # =============================================================================

    def validate(self, addon_id: str) -> bool:
        """Validate an addon before loading.

        Runs the addon's validation hook if available.
        Transition: DISCOVERED → VALIDATED (implicit, goes to LOADED)
        """
        if self.states.get(addon_id) != "DISCOVERED":
            return False

        manifest = self.registry.manifests.get(addon_id)
        if not manifest:
            return False

        # Run validation hook if available
        if manifest.startup_hook:
            try:
                # Import addon module and call validation
                addon_module = self._load_addon_module(addon_id)
                if addon_module and hasattr(addon_module, "validate"):
                    result = addon_module.validate()
                    if not result:
                        self.fault(addon_id)
                        return False
            except Exception:
                self.fault(addon_id)
                return False

        return True

    def load(self, addon_id: str) -> bool:
        """Load an addon.

        Transition: DISCOVERED/VALIDATED → LOADED
        """
        if addon_id not in self.registry.manifests:
            return False

        # Validate first
        if not self.validate(addon_id):
            return False

        try:
            # Load addon module
            addon_module = self._load_addon_module(addon_id)
            if not addon_module:
                self.fault(addon_id)
                return False

            # Register tools, bridges, sinks, etc.
            self._register_addon_components(addon_id, addon_module)

            self.states[addon_id] = "LOADED"
            return True
        except Exception:
            self.fault(addon_id)
            return False

    def start(self, addon_id: str) -> bool:
        """Start an addon (alias for enable).

        Transition: LOADED/DISABLED → ENABLED
        """
        if self.states.get(addon_id) not in {"LOADED", "DISABLED"}:
            return False

        manifest = self.registry.manifests.get(addon_id)
        if manifest and manifest.startup_hook:
            try:
                addon_module = self._load_addon_module(addon_id)
                if addon_module and hasattr(addon_module, "startup"):
                    addon_module.startup()
            except Exception:
                self.fault(addon_id)
                return False

        self.states[addon_id] = "ENABLED"
        return True

    def stop(self, addon_id: str) -> bool:
        """Stop an addon (alias for disable).

        Transition: ENABLED → DISABLED
        """
        if self.states.get(addon_id) != "ENABLED":
            return False

        manifest = self.registry.manifests.get(addon_id)
        if manifest and manifest.shutdown_hook:
            try:
                addon_module = self._load_addon_module(addon_id)
                if addon_module and hasattr(addon_module, "shutdown"):
                    addon_module.shutdown()
            except Exception:
                pass  # Still disable even if shutdown fails

        self.states[addon_id] = "DISABLED"
        return True

    def healthcheck(self, addon_id: str) -> dict[str, Any]:
        """Run health check for an addon.

        Returns health status dict with ok, details, and any errors.
        """
        if addon_id not in self.states:
            return {"ok": False, "error": "addon_not_found", "addon_id": addon_id}

        state = self.states.get(addon_id)
        if state == "FAULTED":
            return {"ok": False, "state": "FAULTED", "error": "addon_is_faulted"}

        manifest = self.registry.manifests.get(addon_id)
        if not manifest:
            return {"ok": False, "error": "manifest_not_found"}

        # Check if addon has healthcheck hook
        if manifest.healthcheck_hook:
            try:
                addon_module = self._load_addon_module(addon_id)
                if addon_module and hasattr(addon_module, manifest.healthcheck_hook):
                    health_fn = getattr(addon_module, manifest.healthcheck_hook)
                    result = health_fn()
                    self._health_cache[addon_id] = result
                    return result
            except Exception as e:
                result = {
                    "ok": False,
                    "error": f"healthcheck_failed: {type(e).__name__}: {e}",
                }
                self._health_cache[addon_id] = result
                return result

        # Default health check: check state
        return {
            "ok": state in {"LOADED", "ENABLED"},
            "state": state,
            "addon_id": addon_id,
        }

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary for all addons.

        Returns aggregated health status for all registered addons.
        """
        summary = {
            "total": len(self.states),
            "enabled": 0,
            "disabled": 0,
            "loaded": 0,
            "faulted": 0,
            "unloaded": 0,
            "discovered": 0,
            "addons": {},
        }

        for addon_id, state in self.states.items():
            if state == "ENABLED":
                summary["enabled"] += 1
            elif state == "DISABLED":
                summary["disabled"] += 1
            elif state == "LOADED":
                summary["loaded"] += 1
            elif state == "FAULTED":
                summary["faulted"] += 1
            elif state == "UNLOADED":
                summary["unloaded"] += 1
            elif state == "DISCOVERED":
                summary["discovered"] += 1

            health = self.healthcheck(addon_id)
            summary["addons"][addon_id] = {
                "state": state,
                "health": health,
            }

        return summary

    def _load_addon_module(self, addon_id: str):
        """Load an addon module by ID."""
        addon_path = (
            self.registry._addons_dir / addon_id / "manifest.py"
            if self.registry._addons_dir
            else None
        )
        if not addon_path or not addon_path.exists():
            return None

        import importlib.util

        spec = importlib.util.spec_from_file_location("manifest", str(addon_path))
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _register_addon_components(self, addon_id: str, module) -> None:
        """Register addon components (tools, bridges, sinks, etc.) with the registry."""
        manifest = self.registry.manifests.get(addon_id)
        if not manifest:
            return

        # Register tools
        for tool_name in manifest.tools or ():
            if hasattr(module, tool_name.replace(".", "_").replace("/", "_")):
                fn = getattr(module, tool_name.replace(".", "_").replace("/", "_"))
                self.registry.register_tool(f"{addon_id}.{tool_name}", fn)

        # Register input bridges
        for bridge_name in manifest.input_bridges or ():
            if hasattr(module, bridge_name):
                bridge = getattr(module, bridge_name)
                self.registry.register_input_bridge(f"{addon_id}.{bridge_name}", bridge)

        # Register output sinks
        for sink_name in manifest.output_sinks or ():
            if hasattr(module, sink_name):
                sink = getattr(module, sink_name)
                self.registry.register_output_sink(f"{addon_id}.{sink_name}", sink)

        # Register audio channels
        for channel_name in manifest.audio_channels or ():
            if hasattr(module, f"{channel_name}_channel"):
                channel = getattr(module, f"{channel_name}_channel")
                self.registry.register_audio_channel(
                    f"{addon_id}.{channel_name}", channel
                )

        # Register permission mapper
        if manifest.permission_mapper and hasattr(module, manifest.permission_mapper):
            mapper = getattr(module, manifest.permission_mapper)
            self.registry.register_permission_mapper(addon_id, mapper)

        # Register healthcheck
        if manifest.healthcheck_hook and hasattr(module, manifest.healthcheck_hook):
            health_fn = getattr(module, manifest.healthcheck_hook)
            self.registry.register_healthcheck(addon_id, health_fn)

        # Register command pack
        if manifest.command_pack:
            self.registry.register_command_pack(addon_id, list(manifest.command_pack))

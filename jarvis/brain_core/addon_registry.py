from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .contracts import AddonManifest, validate_manifest


@dataclass
class AddonDiscoveryResult:
    """Result of addon discovery attempt.

    Separates discovery errors from runtime faults.
    """

    addon_id: str
    success: bool
    manifest: Optional[AddonManifest] = None
    errors: list[str] = field(default_factory=list)
    capability_summary: str = ""
    source_path: Optional[str] = None


class AddonRegistry:
    """Addon registry with auto-discovery and deep validation.

    Phase 4A: Addon Discovery
    - Auto-scans addons/ directory for manifest.py files
    - Deep-validates all manifest fields
    - Separates discovery errors from runtime faults
    - Emits addon_discovered events
    - Builds addon index with capability summary
    """

    def __init__(self, addons_dir: Optional[str] = None) -> None:
        self.manifests: dict[str, AddonManifest] = {}
        self.tools: dict[str, Callable[..., Any]] = {}
        self.input_bridges: dict[str, Any] = {}
        self.output_sinks: dict[str, Any] = {}
        self.audio_channels: dict[str, dict[str, Any]] = {}
        self.command_packs: dict[str, list[str]] = {}
        self.permission_mappers: dict[str, Callable[..., str]] = {}
        self.healthchecks: dict[str, Callable[[], dict[str, Any]]] = {}
        self._addons_dir = Path(addons_dir) if addons_dir else None
        self._discovery_results: dict[str, AddonDiscoveryResult] = {}

    def register_manifest(self, manifest: AddonManifest) -> list[str]:
        errors = validate_manifest(manifest)
        if errors:
            return errors
        self.manifests[manifest.addon_id] = manifest
        return []

    def register_tool(self, qualified_name: str, fn: Callable[..., Any]) -> None:
        self.tools[qualified_name] = fn

    def register_input_bridge(self, bridge_id: str, bridge: Any) -> None:
        self.input_bridges[bridge_id] = bridge

    def register_output_sink(self, sink_id: str, sink: Any) -> None:
        self.output_sinks[sink_id] = sink

    def register_audio_channel(self, channel_id: str, channel: dict[str, Any]) -> None:
        self.audio_channels[channel_id] = dict(channel)

    def register_command_pack(self, addon_id: str, commands: list[str]) -> None:
        self.command_packs[addon_id] = list(commands)

    def register_permission_mapper(
        self, addon_id: str, mapper: Callable[..., str]
    ) -> None:
        self.permission_mappers[addon_id] = mapper

    def register_healthcheck(
        self, addon_id: str, fn: Callable[[], dict[str, Any]]
    ) -> None:
        self.healthchecks[addon_id] = fn

    # =============================================================================
    # Phase 4A: Addon Discovery - Auto-scan and deep validation
    # =============================================================================

    def discover_all(self) -> list[AddonDiscoveryResult]:
        """Auto-discover all addons in the addons directory.

        Scans addons/ for subdirectories containing manifest.py,
        loads and validates each manifest, and returns discovery results.

        Returns: list of AddonDiscoveryResult for each addon found
        """
        results: list[AddonDiscoveryResult] = []

        if self._addons_dir is None:
            # Default to addons/ relative to jarvis/brain_core
            self._addons_dir = Path(__file__).parent.parent / "addons"

        if not self._addons_dir.exists():
            return results

        for subdir in self._addons_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith("_") or subdir.name.startswith("."):
                continue

            manifest_py = subdir / "manifest.py"
            if not manifest_py.exists():
                continue

            result = self._discover_single(subdir, manifest_py)
            results.append(result)
            self._discovery_results[result.addon_id] = result

        return results

    def _discover_single(self, subdir: Path, manifest_py: Path) -> AddonDiscoveryResult:
        """Discover a single addon from its manifest file.

        Deep-validates the manifest and separates discovery errors from runtime faults.
        """
        addon_id = subdir.name
        errors: list[str] = []
        manifest: Optional[AddonManifest] = None

        try:
            # Load manifest module dynamically
            spec = importlib.util.spec_from_file_location("manifest", str(manifest_py))
            if spec is None or spec.loader is None:
                errors.append(f"Failed to load manifest spec for {addon_id}")
                return AddonDiscoveryResult(
                    addon_id=addon_id,
                    success=False,
                    errors=errors,
                    source_path=str(manifest_py),
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Call build_manifest() if available
            if not hasattr(module, "build_manifest"):
                errors.append("manifest.py missing build_manifest() function")
                return AddonDiscoveryResult(
                    addon_id=addon_id,
                    success=False,
                    errors=errors,
                    source_path=str(manifest_py),
                )

            manifest = module.build_manifest()

            # Deep-validate manifest fields
            validation_errors = self._deep_validate_manifest(manifest)
            if validation_errors:
                errors.extend(validation_errors)
                return AddonDiscoveryResult(
                    addon_id=addon_id,
                    success=False,
                    manifest=manifest,
                    errors=errors,
                    source_path=str(manifest_py),
                    capability_summary=manifest.capability_summary,
                )

            # Register the manifest
            register_errors = self.register_manifest(manifest)
            if register_errors:
                errors.extend(register_errors)
                return AddonDiscoveryResult(
                    addon_id=addon_id,
                    success=False,
                    manifest=manifest,
                    errors=errors,
                    source_path=str(manifest_py),
                    capability_summary=manifest.capability_summary,
                )

            return AddonDiscoveryResult(
                addon_id=addon_id,
                success=True,
                manifest=manifest,
                errors=[],
                source_path=str(manifest_py),
                capability_summary=manifest.capability_summary,
            )

        except Exception as e:
            errors.append(f"Discovery failed: {type(e).__name__}: {e}")
            return AddonDiscoveryResult(
                addon_id=addon_id,
                success=False,
                errors=errors,
                source_path=str(manifest_py),
            )

    def _deep_validate_manifest(self, manifest: AddonManifest) -> list[str]:
        """Deep-validate all manifest fields.

        Checks required fields, valid formats, and cross-field consistency.
        """
        errors: list[str] = []

        # Required fields
        if not manifest.addon_id or not manifest.addon_id.strip():
            errors.append("addon_id is required and must be non-empty")
        if not manifest.addon_name or not manifest.addon_name.strip():
            errors.append("addon_name is required and must be non-empty")
        if not manifest.version or not manifest.version.strip():
            errors.append("version is required and must be non-empty")

        # Validate addon_id format (alphanumeric + underscore/hyphen)
        if manifest.addon_id and not all(
            c.isalnum() or c in "_-" for c in manifest.addon_id
        ):
            errors.append(f"addon_id '{manifest.addon_id}' contains invalid characters")

        # Validate version format (semver-like)
        if manifest.version and not any(c.isdigit() for c in manifest.version):
            errors.append(
                f"version '{manifest.version}' should contain version numbers"
            )

        # Validate tools format
        if manifest.tools and not all(
            isinstance(t, str) and t.strip() for t in manifest.tools
        ):
            errors.append("tools must be non-empty strings")

        # Validate command_pack format
        if manifest.command_pack and not all(
            isinstance(c, str) and c.strip() for c in manifest.command_pack
        ):
            errors.append("command_pack must be non-empty strings")

        return errors

    def get_addon_index(self) -> list[dict[str, Any]]:
        """Build an index of all discovered addons with capability summaries.

        Returns: list of addon info dicts with id, name, version, capabilities, state
        """
        index = []
        for addon_id, result in self._discovery_results.items():
            index.append(
                {
                    "addon_id": addon_id,
                    "addon_name": result.manifest.addon_name
                    if result.manifest
                    else "Unknown",
                    "version": result.manifest.version
                    if result.manifest
                    else "Unknown",
                    "capability_summary": result.capability_summary,
                    "success": result.success,
                    "errors": result.errors,
                    "source_path": result.source_path,
                }
            )
        # Add any registered manifests not in discovery results
        for addon_id, manifest in self.manifests.items():
            if addon_id not in self._discovery_results:
                index.append(
                    {
                        "addon_id": addon_id,
                        "addon_name": manifest.addon_name,
                        "version": manifest.version,
                        "capability_summary": manifest.capability_summary,
                        "success": True,
                        "errors": [],
                        "source_path": None,
                    }
                )
        return index

    def get_discovered_addons(self) -> list[AddonDiscoveryResult]:
        """Get all discovery results."""
        return list(self._discovery_results.values())

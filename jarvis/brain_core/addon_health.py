from __future__ import annotations


from .addon_registry import AddonRegistry


class AddonHealthService:
    def __init__(self, registry: AddonRegistry) -> None:
        self.registry = registry

    def run_healthchecks(self) -> dict[str, dict[str, str]]:
        output: dict[str, dict[str, str]] = {}
        for addon_id, fn in self.registry.healthchecks.items():
            try:
                result = fn()
                state = (
                    "addon_healthcheck_passed"
                    if result.get("ok")
                    else "addon_healthcheck_failed"
                )
                output[addon_id] = {"state": state}
            except Exception:
                output[addon_id] = {"state": "addon_healthcheck_failed"}
        return output

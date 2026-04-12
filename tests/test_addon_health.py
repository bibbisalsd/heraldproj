from __future__ import annotations
from jarvis.brain_core.addon_health import AddonHealthService
from jarvis.brain_core.addon_registry import AddonRegistry


def test_addon_health_reports_pass_and_fail():
    registry = AddonRegistry()
    registry.register_healthcheck("ok_addon", lambda: {"ok": True})
    registry.register_healthcheck("bad_addon", lambda: {"ok": False})
    health = AddonHealthService(registry).run_healthchecks()
    assert health["ok_addon"]["state"] == "addon_healthcheck_passed"
    assert health["bad_addon"]["state"] == "addon_healthcheck_failed"

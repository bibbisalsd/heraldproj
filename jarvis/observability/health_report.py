from __future__ import annotations


def build_health_report(
    *, runtime_ok: bool, addon_faults: int, degraded_mode: bool
) -> dict:
    status = (
        "ok" if runtime_ok and addon_faults == 0 and not degraded_mode else "degraded"
    )
    return {
        "status": status,
        "runtime_ok": runtime_ok,
        "addon_faults": addon_faults,
        "degraded_mode": degraded_mode,
    }

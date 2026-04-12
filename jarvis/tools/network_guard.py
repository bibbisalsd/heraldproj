from __future__ import annotations

from jarvis.brain_core.network_guard import NetworkGuard


def validate(url: str) -> dict:
    ok, reason = NetworkGuard().validate_url(url)
    return {"ok": ok, "reason": reason}

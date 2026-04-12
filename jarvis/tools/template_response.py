from __future__ import annotations


def build(message: str, reason: str = "template") -> dict:
    return {"ok": True, "resolved_by": "template", "reason": reason, "text": message}

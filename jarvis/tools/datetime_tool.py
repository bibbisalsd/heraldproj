from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> dict:
    return {"ok": True, "utc": datetime.now(timezone.utc).isoformat()}

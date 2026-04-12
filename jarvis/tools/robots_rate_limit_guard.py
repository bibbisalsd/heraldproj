from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


class RobotsRateLimitGuard:
    def __init__(self, per_domain_requests_per_minute: int = 30) -> None:
        self.limit = per_domain_requests_per_minute
        self._counts = defaultdict(int)
        self._minute = self._current_minute()

    def _current_minute(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")

    def allow(self, domain: str) -> bool:
        minute = self._current_minute()
        if minute != self._minute:
            self._counts.clear()
            self._minute = minute
        self._counts[domain] += 1
        return self._counts[domain] <= self.limit

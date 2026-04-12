"""Route Cache: LRU cache for route decisions and tool results.

Provides:
- Route decision caching (same input → same route within TTL)
- Tool result caching (avoid re-executing identical tool calls)
- Configurable TTL and max size
- Cache hit/miss statistics
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """A single cache entry with TTL."""

    key: str
    value: Any
    created_at: float
    ttl_seconds: float
    hits: int = 0

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_seconds


class LRUCache:
    """Simple LRU cache with TTL expiration."""

    def __init__(self, max_size: int = 200, default_ttl: float = 60.0) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Get value from cache, or None if missing/expired."""
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.is_expired:
            del self._cache[key]
            self._misses += 1
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry.hits += 1
        self._hits += 1
        return entry.value

    def put(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Put value into cache."""
        if key in self._cache:
            del self._cache[key]
        self._cache[key] = CacheEntry(
            key=key,
            value=value,
            created_at=time.monotonic(),
            ttl_seconds=ttl or self._default_ttl,
        )
        # Evict oldest if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(self, key: str) -> bool:
        """Invalidate a specific cache entry."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            "total_requests": total,
        }


class RouteCache:
    """Cache for route decisions.

    Caches the route decision for identical normalized text inputs.
    Short TTL (30s) to avoid stale routing when context changes.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 30.0) -> None:
        self._cache = LRUCache(max_size=max_size, default_ttl=ttl_seconds)

    def get_route(self, normalized_text: str, bg1_busy: bool) -> Any | None:
        """Get cached route decision."""
        key = f"route:{normalized_text}:bg1={bg1_busy}"
        return self._cache.get(key)

    def cache_route(
        self,
        normalized_text: str,
        bg1_busy: bool,
        decision: Any,
    ) -> None:
        """Cache a route decision."""
        key = f"route:{normalized_text}:bg1={bg1_busy}"
        self._cache.put(key, decision)

    def invalidate_all(self) -> None:
        """Invalidate all cached routes."""
        self._cache.clear()

    def stats(self) -> dict[str, Any]:
        return self._cache.stats()


class ToolResultCache:
    """Cache for tool execution results.

    Caches results of idempotent tool calls (time queries, calculations, etc.)
    Longer TTL (5min) for stable results, shorter for time-sensitive tools.
    """

    # Tools with short TTL (time-sensitive)
    SHORT_TTL_TOOLS = {"local_now", "utc_now_iso", "screen_capture", "active_window"}
    SHORT_TTL_SECONDS = 5.0

    # Tools with medium TTL
    MEDIUM_TTL_TOOLS = {"web_fetch", "website_text"}
    MEDIUM_TTL_SECONDS = 120.0

    # All other tools get long TTL
    LONG_TTL_SECONDS = 300.0

    def __init__(self, max_size: int = 150) -> None:
        self._cache = LRUCache(max_size=max_size, default_ttl=self.LONG_TTL_SECONDS)

    def _get_ttl(self, tool_name: str) -> float:
        if tool_name in self.SHORT_TTL_TOOLS:
            return self.SHORT_TTL_SECONDS
        if tool_name in self.MEDIUM_TTL_TOOLS:
            return self.MEDIUM_TTL_SECONDS
        return self.LONG_TTL_SECONDS

    def get_result(self, tool_name: str, args_key: str) -> Any | None:
        """Get cached tool result."""
        key = f"tool:{tool_name}:{args_key}"
        return self._cache.get(key)

    def cache_result(
        self,
        tool_name: str,
        args_key: str,
        result: Any,
    ) -> None:
        """Cache a tool result."""
        key = f"tool:{tool_name}:{args_key}"
        ttl = self._get_ttl(tool_name)
        self._cache.put(key, result, ttl=ttl)

    def invalidate_tool(self, tool_name: str) -> None:
        """Invalidate all cached results for a specific tool."""
        keys_to_remove = [
            key for key in self._cache._cache if key.startswith(f"tool:{tool_name}:")
        ]
        for key in keys_to_remove:
            self._cache.invalidate(key)

    def stats(self) -> dict[str, Any]:
        return self._cache.stats()

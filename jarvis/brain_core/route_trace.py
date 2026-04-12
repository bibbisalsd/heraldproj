"""Route Trace: Structured route decision logging with candidate scoring.

Provides:
- Per-turn route decision recording
- Candidate scoring audit trail
- Route decision persistence for CRSIS analysis
- Voice-friendly route explanations
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RouteCandidateRecord:
    """Record of a single routing candidate."""

    source: str  # exact, deterministic, tool_first, semantic, classifier
    intent: str
    lane: str
    confidence: float
    reason: str
    tool_name: str | None = None
    latency_class: str = "moderate"
    rejected_reason: str | None = None


@dataclass
class RouteDecisionRecord:
    """Complete record of a route decision for a turn."""

    turn_id: str
    timestamp: str
    query: str
    normalized_query: str
    candidates: list[RouteCandidateRecord] = field(default_factory=list)
    selected_source: str = ""
    selected_intent: str = ""
    selected_lane: str = ""
    selected_confidence: float = 0.0
    cache_hit: bool = False
    elapsed_ms: float = 0.0
    context_rewrite: str | None = None
    bg1_busy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "query": self.query[:200],
            "normalized_query": self.normalized_query[:200],
            "candidates": [asdict(c) for c in self.candidates],
            "selected": {
                "source": self.selected_source,
                "intent": self.selected_intent,
                "lane": self.selected_lane,
                "confidence": self.selected_confidence,
            },
            "cache_hit": self.cache_hit,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "context_rewrite": self.context_rewrite,
            "bg1_busy": self.bg1_busy,
        }


class RouteTraceLogger:
    """Persistent route trace logger for debugging and CRSIS analysis.

    Maintains a rolling buffer of recent route decisions and
    writes to a JSONL file for post-hoc analysis.
    """

    def __init__(
        self,
        log_dir: str = "./logs",
        max_recent: int = 50,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._recent: deque[RouteDecisionRecord] = deque(maxlen=max_recent)

    def record(self, decision: RouteDecisionRecord) -> None:
        """Record a route decision."""
        self._recent.append(decision)
        self._write_to_jsonl(decision)

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent route decisions."""
        return [d.to_dict() for d in list(self._recent)[-limit:]]

    def get_route_stats(self) -> dict[str, Any]:
        """Get routing statistics from recent decisions."""
        if not self._recent:
            return {"total": 0}

        sources: dict[str, int] = {}
        lanes: dict[str, int] = {}
        intents: dict[str, int] = {}
        cache_hits = 0
        total_ms = 0.0

        for d in self._recent:
            sources[d.selected_source] = sources.get(d.selected_source, 0) + 1
            lanes[d.selected_lane] = lanes.get(d.selected_lane, 0) + 1
            intents[d.selected_intent] = intents.get(d.selected_intent, 0) + 1
            if d.cache_hit:
                cache_hits += 1
            total_ms += d.elapsed_ms

        total = len(self._recent)
        return {
            "total": total,
            "sources": sources,
            "lanes": lanes,
            "top_intents": dict(sorted(intents.items(), key=lambda x: -x[1])[:10]),
            "cache_hit_rate": round(cache_hits / total, 3) if total > 0 else 0.0,
            "avg_route_ms": round(total_ms / total, 1) if total > 0 else 0.0,
        }

    def _write_to_jsonl(self, decision: RouteDecisionRecord) -> None:
        """Write decision to JSONL file."""
        try:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            path = self._log_dir / f"jarvis_routes_{day}.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(decision.to_dict(), ensure_ascii=True, default=str)
                    + "\n"
                )
        except OSError:
            pass  # Non-critical logging

from __future__ import annotations

from dataclasses import dataclass


from .contracts import IngressEnvelope


HEAVY_KEYWORDS: set[str] = {
    "research",
    "analyze",
    "analysis",
    "crawl",
    "scrape",
    "refactor",
    "debug",
    "generate code",
    "summarize file",
}


@dataclass
class LaneDecision:
    lane: str
    reason: str


class LaneCoordinator:
    def classify(self, text: str) -> LaneDecision:
        normalized = text.lower().strip()
        if any(key in normalized for key in HEAVY_KEYWORDS):
            return LaneDecision(lane="bg1", reason="heavy_request")
        return LaneDecision(lane="realtime", reason="quick_or_general")

    def route(
        self, envelope: IngressEnvelope, bg1_is_busy: bool = False
    ) -> LaneDecision:
        decision = self.classify(envelope.text)
        if decision.lane == "bg1" and bg1_is_busy:
            return LaneDecision(lane="realtime", reason="BG1_BUSY_ACTIVE")
        return decision

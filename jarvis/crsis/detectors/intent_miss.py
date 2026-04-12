"""IntentMissDetector - Track and analyze intent routing misses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.utils.time_utils import utc_now_iso


@dataclass(frozen=True)
class IntentMiss:
    """Record of an intent that was missed by the router."""

    turn_id: str
    utterance: str
    normalized_text: str
    routed_intent: str
    match_type: str
    lane: str
    miss_reason: str  # "fallback_to_general", "user_correction", "low_confidence"
    expected_intent: str | None = None
    confidence: float = 0.0
    timestamp: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntentMissPattern:
    """Aggregated pattern from multiple intent misses."""

    pattern_id: str
    utterance_pattern: str  # Normalized pattern or regex
    miss_count: int
    common_routed_intent: str
    expected_intent: str | None
    first_seen: str
    last_seen: str
    severity: str  # "low", "medium", "high"


class IntentMissDetector:
    """Detect and aggregate intent routing misses.

    Tracks:
    - Fallback to general_chat (potential missed intent)
    - User corrections after routing
    - Low confidence semantic matches
    """

    def __init__(self, max_history: int = 500) -> None:
        self._misses: list[IntentMiss] = []
        self._max_history = max_history
        self._patterns: dict[str, IntentMissPattern] = {}

    def log_miss(
        self,
        turn_id: str,
        utterance: str,
        normalized_text: str,
        routed_intent: str,
        match_type: str,
        lane: str,
        miss_reason: str,
        expected_intent: str | None = None,
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> IntentMiss:
        """Log an intent miss."""
        miss = IntentMiss(
            turn_id=turn_id,
            utterance=utterance,
            normalized_text=normalized_text,
            routed_intent=routed_intent,
            match_type=match_type,
            lane=lane,
            miss_reason=miss_reason,
            expected_intent=expected_intent,
            confidence=confidence,
            metadata=metadata or {},
        )
        self._misses.append(miss)

        # Trim history
        if len(self._misses) > self._max_history:
            self._misses = self._misses[-self._max_history :]

        # Update patterns
        self._update_patterns(miss)

        return miss

    def log_correction(
        self,
        turn_id: str,
        original_utterance: str,
        original_intent: str,
        correction_text: str,
    ) -> IntentMiss:
        """Log a user correction (explicit feedback)."""
        return self.log_miss(
            turn_id=turn_id,
            utterance=original_utterance,
            normalized_text=original_utterance.lower(),
            routed_intent=original_intent,
            match_type="correction",
            lane="realtime",
            miss_reason="user_correction",
            expected_intent=None,  # Inferred from correction
            metadata={"correction_text": correction_text},
        )

    def get_misses(
        self,
        turn_id: str | None = None,
        miss_reason: str | None = None,
        limit: int = 100,
    ) -> list[IntentMiss]:
        """Get intent misses with optional filtering."""
        results = self._misses

        if turn_id:
            results = [m for m in results if m.turn_id == turn_id]
        if miss_reason:
            results = [m for m in results if m.miss_reason == miss_reason]

        return results[-limit:]

    def get_patterns(self, min_count: int = 3) -> list[IntentMissPattern]:
        """Get aggregated patterns with minimum occurrence count."""
        return [p for p in self._patterns.values() if p.miss_count >= min_count]

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics."""
        total = len(self._misses)
        by_reason: dict[str, int] = {}
        by_intent: dict[str, int] = {}

        for miss in self._misses:
            by_reason[miss.miss_reason] = by_reason.get(miss.miss_reason, 0) + 1
            by_intent[miss.routed_intent] = by_intent.get(miss.routed_intent, 0) + 1

        return {
            "total_misses": total,
            "by_reason": by_reason,
            "by_routed_intent": by_intent,
            "patterns_detected": len(self._patterns),
        }

    def _update_patterns(self, miss: IntentMiss) -> None:
        """Update pattern aggregation from a new miss."""
        # Create a pattern key from normalized text (first 3 words)
        words = miss.normalized_text.split()[:3]
        pattern_key = " ".join(words) if len(words) >= 2 else miss.normalized_text

        if pattern_key in self._patterns:
            existing = self._patterns[pattern_key]
            # Update existing pattern
            self._patterns[pattern_key] = IntentMissPattern(
                pattern_id=existing.pattern_id,
                utterance_pattern=pattern_key,
                miss_count=existing.miss_count + 1,
                common_routed_intent=miss.routed_intent,
                expected_intent=miss.expected_intent or existing.expected_intent,
                first_seen=existing.first_seen,
                last_seen=miss.timestamp,
                severity=self._calc_severity(existing.miss_count + 1),
            )
        else:
            # Create new pattern
            import hashlib

            pattern_id = hashlib.sha256(pattern_key.encode()).hexdigest()[:8]
            self._patterns[pattern_key] = IntentMissPattern(
                pattern_id=pattern_id,
                utterance_pattern=pattern_key,
                miss_count=1,
                common_routed_intent=miss.routed_intent,
                expected_intent=miss.expected_intent,
                first_seen=miss.timestamp,
                last_seen=miss.timestamp,
                severity="low",
            )

    def _calc_severity(self, count: int) -> str:
        """Calculate severity based on occurrence count."""
        if count >= 10:
            return "high"
        elif count >= 5:
            return "medium"
        return "low"

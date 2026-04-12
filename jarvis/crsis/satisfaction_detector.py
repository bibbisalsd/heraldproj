"""SatisfactionDetector - Detect user satisfaction signals from conversation."""

from __future__ import annotations


from dataclasses import dataclass
from typing import Any

from jarvis.crsis.contracts import SatisfactionSignal


@dataclass(frozen=True)
class SatisfactionDetectionResult:
    """Result of satisfaction detection."""

    signal: SatisfactionSignal | None
    raw_indicators: dict[str, Any]


class SatisfactionDetector:
    """Detect user satisfaction signals from conversation patterns.

    Detects:
    - correction: User corrects or re-does something
    - re_ask: User asks the same question again
    - acceptance: User accepts/continues with response
    - abandonment: User abandons the task or conversation
    """

    def __init__(self) -> None:
        self._correction_patterns = [
            "no,",
            "not that",
            "wrong",
            "i meant",
            "i said",
            "that's not",
            "that's not what",
            "stop",
            "cancel",
        ]
        self._re_ask_patterns: list[str] = []  # Populated from conversation context
        self._acceptance_patterns = [
            "yes",
            "thanks",
            "thank you",
            "perfect",
            "great",
            "good",
            "ok",
            "okay",
            "that works",
            "continue",
            "go ahead",
        ]
        self._abandonment_patterns = [
            "never mind",
            "forget it",
            "it's fine",
            "doesn't matter",
        ]

    def detect(
        self,
        user_message: str,
        conversation_history: list[dict[str, Any]],
        follow_up_window_active: bool = False,
    ) -> SatisfactionDetectionResult:
        """Detect satisfaction signal from user message and conversation.

        Args:
            user_message: Current user message
            conversation_history: list of {role, content} dicts
            follow_up_window_active: Whether follow-up repair window is active

        Returns:
            SatisfactionDetectionResult with detected signal (or None)
        """
        message_lower = user_message.lower().strip()
        raw_indicators: dict[str, Any] = {
            "correction_matches": [],
            "re_ask_detected": False,
            "acceptance_matches": [],
            "abandonment_matches": [],
            "follow_up_window": follow_up_window_active,
        }

        # Check for correction patterns
        for pattern in self._correction_patterns:
            if pattern in message_lower:
                raw_indicators["correction_matches"].append(pattern)

        # Check for re-ask (same intent as recent messages)
        if conversation_history:
            recent_user_messages = [
                m["content"].lower()
                for m in conversation_history[-6:]  # Last 3 turns
                if m.get("role") == "user"
            ]
            # Simple heuristic: if current message is similar to a previous one
            for prev in recent_user_messages[:-1]:  # Exclude most recent (current)
                if self._similarity(message_lower, prev) > 0.7:
                    raw_indicators["re_ask_detected"] = True
                    break

        # Check for acceptance patterns
        for pattern in self._acceptance_patterns:
            if message_lower.startswith(pattern) or message_lower == pattern:
                raw_indicators["acceptance_matches"].append(pattern)

        # Check for abandonment patterns
        for pattern in self._abandonment_patterns:
            if pattern in message_lower:
                raw_indicators["abandonment_matches"].append(pattern)

        # Determine signal type
        signal = self._determine_signal(raw_indicators, follow_up_window_active)

        return SatisfactionDetectionResult(signal=signal, raw_indicators=raw_indicators)

    def _determine_signal(
        self, indicators: dict[str, Any], follow_up_window_active: bool
    ) -> SatisfactionSignal | None:
        """Determine signal type from indicators."""
        import uuid
        from datetime import datetime, timezone

        turn_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Priority: correction > re_ask > abandonment > acceptance

        if indicators["correction_matches"]:
            return SatisfactionSignal(
                turn_id=turn_id,
                signal_type="correction",
                confidence=0.8,
                evidence={"matches": indicators["correction_matches"]},
                timestamp=timestamp,
            )

        if indicators["re_ask_detected"]:
            return SatisfactionSignal(
                turn_id=turn_id,
                signal_type="re_ask",
                confidence=0.7,
                evidence={"re_ask": True},
                timestamp=timestamp,
            )

        if indicators["abandonment_matches"]:
            return SatisfactionSignal(
                turn_id=turn_id,
                signal_type="abandonment",
                confidence=0.6,
                evidence={"matches": indicators["abandonment_matches"]},
                timestamp=timestamp,
            )

        if indicators["acceptance_matches"]:
            return SatisfactionSignal(
                turn_id=turn_id,
                signal_type="acceptance",
                confidence=0.5,
                evidence={"matches": indicators["acceptance_matches"]},
                timestamp=timestamp,
            )

        return None

    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity (0-1)."""
        # Token-based Jaccard similarity
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        return intersection / union if union > 0 else 0.0

    def add_correction_pattern(self, pattern: str) -> None:
        """Add a correction pattern."""
        if pattern not in self._correction_patterns:
            self._correction_patterns.append(pattern)

    def add_acceptance_pattern(self, pattern: str) -> None:
        """Add an acceptance pattern."""
        if pattern not in self._acceptance_patterns:
            self._acceptance_patterns.append(pattern)

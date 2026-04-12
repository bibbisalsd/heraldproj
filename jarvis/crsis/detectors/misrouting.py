"""MisroutingDetector - Detect systematically misrouted intents."""

from __future__ import annotations


import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MisroutingFinding:
    """Finding for misrouted intent."""

    intent: str
    correction_count: int
    dispatch_count: int
    correction_rate: float
    examples: list[str]


class MisroutingDetector:
    """Detect systematically misrouted intents.

    Analyzes intent dispatch events and correction signals
    to identify intents that are frequently routed incorrectly.
    """

    def __init__(self) -> None:
        self._dispatch_counts: dict[str, int] = {}
        self._correction_counts: dict[str, int] = {}
        self._last_proposal_time: dict[str, float] = {}

    def record_dispatch(self, intent: str) -> None:
        """Record an intent dispatch."""
        self._dispatch_counts[intent] = self._dispatch_counts.get(intent, 0) + 1

    def record_correction(self, intent: str) -> None:
        """Record a correction for an intent."""
        self._correction_counts[intent] = self._correction_counts.get(intent, 0) + 1

    def detect(
        self, min_corrections: int = 20, min_rate: float = 0.5
    ) -> list[MisroutingFinding]:
        """Detect misrouted intents.

        Args:
            min_corrections: Minimum number of corrections to flag (P3-7: raised to 20)
            min_rate: Minimum correction rate to flag (P3-7: raised to 0.5)

        Returns: list of MisroutingFinding for flagged intents
        """
        findings = []
        now = time.time()

        for intent, corrections in self._correction_counts.items():
            # Check 24h cooldown (P3-7)
            last_time = self._last_proposal_time.get(intent, 0)
            if now - last_time < 86400: # 24 hours in seconds
                continue

            if corrections < min_corrections:
                continue

            dispatches = self._dispatch_counts.get(intent, 1)
            rate = corrections / dispatches

            if rate >= min_rate:
                # Mark proposal time
                self._last_proposal_time[intent] = now
                
                findings.append(
                    MisroutingFinding(
                        intent=intent,
                        correction_count=corrections,
                        dispatch_count=dispatches,
                        correction_rate=round(rate, 3),
                        examples=[f"Intent '{intent}' corrected {corrections} times"],
                    )
                )

        return findings

    def get_statistics(self) -> dict[str, Any]:
        """Get misrouting statistics."""
        total_dispatches = sum(self._dispatch_counts.values())
        total_corrections = sum(self._correction_counts.values())

        return {
            "total_dispatches": total_dispatches,
            "total_corrections": total_corrections,
            "overall_correction_rate": round(total_corrections / total_dispatches, 3)
            if total_dispatches > 0
            else 0.0,
            "intents_tracked": len(self._dispatch_counts),
            "intents_with_corrections": len(self._correction_counts),
        }

    def reset(self) -> None:
        """Reset all counters."""
        self._dispatch_counts.clear()
        self._correction_counts.clear()

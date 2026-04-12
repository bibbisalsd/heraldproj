"""Latency Budget: Stage-level latency enforcement and percentile tracking.

Provides:
- Per-stage latency budgets with warning/critical thresholds
- p50/p95 percentile tracking for all stages
- Budget violation alerting
- Turn-level latency summary
- Historical latency analysis
"""

from __future__ import annotations

import bisect
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class StageBudget:
    """Latency budget for a pipeline stage."""

    stage: str
    target_ms: float  # Ideal latency
    warning_ms: float  # Warning threshold
    critical_ms: float  # Critical threshold (potential UX problem)
    description: str = ""


# ── Stage Budgets ────────────────────────────────────────────────
# Based on plan targets for voice-first UX

STAGE_BUDGETS: dict[str, StageBudget] = {
    "ingress": StageBudget(
        stage="ingress",
        target_ms=5.0,
        warning_ms=15.0,
        critical_ms=40.0,
        description="Raw input acceptance and normalization",
    ),
    "normalize": StageBudget(
        stage="normalize",
        target_ms=8.0,
        warning_ms=25.0,
        critical_ms=80.0,
        description="STT correction and profile mapping",
    ),
    "resolve": StageBudget(
        stage="resolve",
        target_ms=8.0,
        warning_ms=25.0,
        critical_ms=80.0,
        description="Reference resolution (it/that/they)",
    ),
    "route": StageBudget(
        stage="route",
        target_ms=12.0,
        warning_ms=40.0,
        critical_ms=120.0,
        description="Intent classification and lane selection",
    ),
    "memory_retrieve": StageBudget(
        stage="memory_retrieve",
        target_ms=15.0,
        warning_ms=40.0,
        critical_ms=150.0,
        description="Memory retrieval across namespaces",
    ),
    "tool_execute": StageBudget(
        stage="tool_execute",
        target_ms=80.0,
        warning_ms=400.0,
        critical_ms=2500.0,
        description="Tool execution (realtime lane)",
    ),
    "evidence_compile": StageBudget(
        stage="evidence_compile",
        target_ms=8.0,
        warning_ms=25.0,
        critical_ms=80.0,
        description="Evidence packet compilation",
    ),
    "llm_render": StageBudget(
        stage="llm_render",
        target_ms=800.0,
        warning_ms=3000.0,
        critical_ms=8000.0,
        description="LLM response generation (CPU inference)",
    ),
    "speech_format": StageBudget(
        stage="speech_format",
        target_ms=3.0,
        warning_ms=10.0,
        critical_ms=30.0,
        description="Speech formatting for TTS",
    ),
    "tts_speak": StageBudget(
        stage="tts_speak",
        target_ms=150.0,
        warning_ms=800.0,
        critical_ms=2500.0,
        description="TTS speech synthesis and playback",
    ),
    "total_turn": StageBudget(
        stage="total_turn",
        target_ms=1200.0,
        warning_ms=4000.0,
        critical_ms=12000.0,
        description="Total turn latency (ingress to speech)",
    ),
}


@dataclass
class BudgetViolation:
    """A budget violation event."""

    stage: str
    actual_ms: float
    budget_ms: float
    severity: str  # "warning" or "critical"
    timestamp: float
    turn_id: str = ""


@dataclass
class LatencyPercentiles:
    """p50/p95/p99 latency percentiles for a stage."""

    stage: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    sample_count: int
    min_ms: float
    max_ms: float
    mean_ms: float


class LatencyTracker:
    """Track per-stage latencies and compute percentiles.

    Uses sorted insertion for efficient percentile computation
    without external dependencies.
    """

    def __init__(self, max_samples: int = 500) -> None:
        self._max_samples = max_samples
        # Sorted latency samples per stage
        self._samples: dict[str, list[float]] = defaultdict(list)
        self._totals: dict[str, float] = defaultdict(float)
        self._counts: dict[str, int] = defaultdict(int)

    def record(self, stage: str, latency_ms: float) -> None:
        """Record a latency sample."""
        samples = self._samples[stage]
        bisect.insort(samples, latency_ms)
        self._totals[stage] += latency_ms
        self._counts[stage] += 1

        # Trim to max samples (remove oldest by position, not value)
        if len(samples) > self._max_samples:
            # Remove median-ish value to maintain distribution shape
            mid = len(samples) // 2
            samples.pop(mid)

    def percentile(self, stage: str, p: float) -> float:
        """Get a specific percentile for a stage."""
        samples = self._samples.get(stage, [])
        if not samples:
            return 0.0
        idx = int(len(samples) * p / 100.0)
        idx = min(idx, len(samples) - 1)
        return samples[idx]

    def get_percentiles(self, stage: str) -> LatencyPercentiles:
        """Get p50/p95/p99 for a stage."""
        samples = self._samples.get(stage, [])
        count = self._counts.get(stage, 0)
        total = self._totals.get(stage, 0.0)

        if not samples:
            return LatencyPercentiles(
                stage=stage,
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                sample_count=0,
                min_ms=0.0,
                max_ms=0.0,
                mean_ms=0.0,
            )

        return LatencyPercentiles(
            stage=stage,
            p50_ms=samples[len(samples) // 2],
            p95_ms=samples[int(len(samples) * 0.95)]
            if len(samples) > 1
            else samples[0],
            p99_ms=samples[int(len(samples) * 0.99)]
            if len(samples) > 1
            else samples[0],
            sample_count=count,
            min_ms=samples[0],
            max_ms=samples[-1],
            mean_ms=total / count if count > 0 else 0.0,
        )

    def get_all_percentiles(self) -> dict[str, LatencyPercentiles]:
        """Get percentiles for all tracked stages."""
        return {stage: self.get_percentiles(stage) for stage in self._samples}


class LatencyBudgetEnforcer:
    """Enforce latency budgets and track violations.

    Checks each stage timing against its budget and logs violations.
    Also feeds latency samples to the percentile tracker.
    """

    def __init__(
        self,
        budgets: dict[str, StageBudget] | None = None,
        tracker: LatencyTracker | None = None,
    ) -> None:
        self._budgets = budgets or STAGE_BUDGETS
        self._tracker = tracker or LatencyTracker()
        self._violations: list[BudgetViolation] = []
        self._max_violations: int = 200

    @property
    def tracker(self) -> LatencyTracker:
        return self._tracker

    def check_stage(
        self,
        stage: str,
        elapsed_ms: float,
        turn_id: str = "",
    ) -> BudgetViolation | None:
        """Check a stage timing against its budget.

        Also records the timing for percentile tracking.

        Args:
            stage: Pipeline stage name
            elapsed_ms: Actual latency in milliseconds
            turn_id: Turn ID for correlation

        Returns:
            BudgetViolation if threshold exceeded, None otherwise
        """
        # Always record for percentile tracking
        self._tracker.record(stage, elapsed_ms)

        budget = self._budgets.get(stage)
        if not budget:
            return None

        violation = None
        if elapsed_ms > budget.critical_ms:
            violation = BudgetViolation(
                stage=stage,
                actual_ms=elapsed_ms,
                budget_ms=budget.critical_ms,
                severity="critical",
                timestamp=time.monotonic(),
                turn_id=turn_id,
            )
        elif elapsed_ms > budget.warning_ms:
            violation = BudgetViolation(
                stage=stage,
                actual_ms=elapsed_ms,
                budget_ms=budget.warning_ms,
                severity="warning",
                timestamp=time.monotonic(),
                turn_id=turn_id,
            )

        if violation:
            self._violations.append(violation)
            if len(self._violations) > self._max_violations:
                self._violations = self._violations[-self._max_violations :]

        return violation

    def check_turn_total(
        self,
        total_ms: float,
        turn_id: str = "",
    ) -> BudgetViolation | None:
        """Check total turn latency."""
        return self.check_stage("total_turn", total_ms, turn_id)

    def get_recent_violations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent budget violations."""
        return [
            {
                "stage": v.stage,
                "actual_ms": round(v.actual_ms, 1),
                "budget_ms": round(v.budget_ms, 1),
                "severity": v.severity,
                "turn_id": v.turn_id,
                "over_by_ms": round(v.actual_ms - v.budget_ms, 1),
            }
            for v in self._violations[-limit:]
        ]

    def get_health_summary(self) -> dict[str, Any]:
        """Get overall latency health summary."""
        all_percentiles = self._tracker.get_all_percentiles()
        violations_last_10 = [
            v for v in self._violations[-50:] if v.severity == "critical"
        ]

        stages_over_budget = []
        for stage, pctl in all_percentiles.items():
            budget = self._budgets.get(stage)
            if budget and pctl.p95_ms > budget.warning_ms:
                stages_over_budget.append(
                    {
                        "stage": stage,
                        "p95_ms": round(pctl.p95_ms, 1),
                        "budget_warning_ms": budget.warning_ms,
                    }
                )

        return {
            "total_violations": len(self._violations),
            "critical_violations_recent": len(violations_last_10),
            "stages_over_budget": stages_over_budget,
            "percentiles": {
                stage: {
                    "p50": round(p.p50_ms, 1),
                    "p95": round(p.p95_ms, 1),
                    "p99": round(p.p99_ms, 1),
                    "count": p.sample_count,
                }
                for stage, p in all_percentiles.items()
            },
        }

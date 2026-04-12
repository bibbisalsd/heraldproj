from __future__ import annotations

from typing import Any

from .contracts import CRSISSignal, CRSISSnapshot
from .engine import CRSISEngine


def build_ops_health_signals(summary: dict[str, Any]) -> list[CRSISSignal]:
    """Map ops-history health summary into CRSIS signals."""

    health = summary.get("health", {})
    thresholds = health.get("thresholds", {}) if isinstance(health, dict) else {}

    coverage = _to_float(
        health.get("voice_smoke_coverage", 0.0) if isinstance(health, dict) else 0.0
    )
    repeat_rate = _to_float(
        health.get("repeat_fallback_rate", 0.0) if isinstance(health, dict) else 0.0
    )
    mic_rate = _to_float(
        health.get("mic_unavailable_rate", 0.0) if isinstance(health, dict) else 0.0
    )

    min_coverage = _to_float(
        thresholds.get("min_voice_smoke_coverage", 0.5)
        if isinstance(thresholds, dict)
        else 0.5
    )
    max_repeat = _to_float(
        thresholds.get("max_repeat_fallback_rate", 0.25)
        if isinstance(thresholds, dict)
        else 0.25
    )
    max_mic = _to_float(
        thresholds.get("max_mic_unavailable_rate", 0.25)
        if isinstance(thresholds, dict)
        else 0.25
    )

    return [
        CRSISSignal(
            key="voice_smoke_coverage",
            value=coverage,
            threshold=min_coverage,
            comparator="lt",
            severity="warn",
            message=f"Voice smoke coverage {coverage:.2f} is below {min_coverage:.2f}.",
        ),
        CRSISSignal(
            key="repeat_fallback_rate",
            value=repeat_rate,
            threshold=max_repeat,
            comparator="gt",
            severity="warn",
            message=f"Repeat fallback rate {repeat_rate:.2f} is above {max_repeat:.2f}.",
        ),
        CRSISSignal(
            key="mic_unavailable_rate",
            value=mic_rate,
            threshold=max_mic,
            comparator="gt",
            severity="warn",
            message=f"Mic unavailable rate {mic_rate:.2f} is above {max_mic:.2f}.",
        ),
    ]


def evaluate_ops_summary(
    summary: dict[str, Any],
    source: str = "ops_history",
) -> dict[str, Any]:
    """Evaluate ops summary with CRSIS defaults and return a compact view."""

    snapshot = evaluate_ops_snapshot(summary, source=source)
    return {
        "timestamp": snapshot.timestamp,
        "source": snapshot.source,
        "status": snapshot.status,
        "signals": [signal.key for signal in snapshot.signals],
        "findings": [
            {
                "signal_key": finding.signal_key,
                "severity": finding.severity,
                "message": finding.message,
            }
            for finding in snapshot.findings
        ],
        "metadata": snapshot.metadata,
    }


def evaluate_ops_snapshot(
    summary: dict[str, Any],
    source: str = "ops_history",
) -> CRSISSnapshot:
    """Evaluate ops summary with CRSIS defaults and return a structured snapshot."""

    engine = CRSISEngine()
    return engine.evaluate(
        signals=build_ops_health_signals(summary),
        source=source,
        metadata={"report_count": _to_int(summary.get("report_count", 0))},
    )


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

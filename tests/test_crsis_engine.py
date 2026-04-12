from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis.crsis import (
    CRSISEngine,
    CRSISSignal,
    build_ops_health_signals,
    evaluate_ops_summary,
    list_snapshot_files,
    persist_snapshot,
    prune_snapshots,
    read_snapshot_log,
)


def _signal(
    key: str,
    value: float,
    threshold: float,
    comparator: str = "gt",
    severity: str = "warn",
    message: str = "",
) -> CRSISSignal:
    return CRSISSignal(
        key=key,
        value=value,
        threshold=threshold,
        comparator=comparator,
        severity=severity,
        message=message,
    )


def test_crsis_engine_ok_when_no_signal_breaches() -> None:
    engine = CRSISEngine()
    snapshot = engine.evaluate(signals=[_signal("repeat_fallback_rate", 0.10, 0.25, comparator="gt")])
    assert snapshot.status == "ok"
    assert snapshot.findings == ()


def test_crsis_engine_warn_on_threshold_breach() -> None:
    engine = CRSISEngine()
    snapshot = engine.evaluate(
        signals=[_signal("repeat_fallback_rate", 0.30, 0.25, comparator="gt", message="repeat too high")]
    )
    assert snapshot.status == "warn"
    assert len(snapshot.findings) == 1
    assert snapshot.findings[0].message == "repeat too high"


def test_crsis_engine_critical_dominates_warn() -> None:
    engine = CRSISEngine()
    snapshot = engine.evaluate(
        signals=[
            _signal("repeat_fallback_rate", 0.30, 0.25, comparator="gt", severity="warn"),
            _signal("mic_unavailable_rate", 0.90, 0.25, comparator="gt", severity="critical"),
        ]
    )
    assert snapshot.status == "critical"
    severities = {finding.severity for finding in snapshot.findings}
    assert "critical" in severities


def test_crsis_engine_invalid_comparator_raises() -> None:
    engine = CRSISEngine()
    with pytest.raises(ValueError):
        engine.evaluate(signals=[_signal("bad", 1.0, 0.0, comparator="between")])


def test_persist_snapshot_writes_jsonl_and_latest(tmp_path: Path) -> None:
    snapshot = CRSISEngine().evaluate(signals=[_signal("repeat_fallback_rate", 0.30, 0.25)])
    paths = persist_snapshot(snapshot, log_dir=str(tmp_path))

    jsonl = Path(paths["jsonl_path"])
    latest = Path(paths["latest_path"])
    assert jsonl.exists()
    assert latest.exists()

    loaded = read_snapshot_log(log_dir=str(tmp_path))
    assert len(loaded) == 1
    assert loaded[0]["status"] == "warn"


def test_read_snapshot_log_nonexistent_date_is_empty(tmp_path: Path) -> None:
    assert read_snapshot_log(log_dir=str(tmp_path), date_str="1999-01-01") == []


def test_list_snapshot_files_sorted_newest_first(tmp_path: Path) -> None:
    first = tmp_path / "jarvis_crsis_2026-03-30.jsonl"
    second = tmp_path / "jarvis_crsis_2026-03-31.jsonl"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    os.utime(first, (1_700_000_000, 1_700_000_000))
    os.utime(second, (1_700_000_100, 1_700_000_100))
    files = list_snapshot_files(log_dir=str(tmp_path))
    assert files[0] == str(second)
    assert files[1] == str(first)


def test_prune_snapshots_deletes_old_files(tmp_path: Path) -> None:
    engine = CRSISEngine()
    persisted = persist_snapshot(engine.evaluate([_signal("a", 1.0, 0.5)]), log_dir=str(tmp_path))
    jsonl = persisted["jsonl_path"]
    old_ts = datetime.now(timezone.utc).timestamp() - (40 * 24 * 3600)
    os.utime(jsonl, (old_ts, old_ts))

    result = prune_snapshots(log_dir=str(tmp_path), retention_days=7)
    assert result["deleted_count"] == 1
    assert jsonl in result["deleted_files"]


def test_build_ops_health_signals_maps_health_summary() -> None:
    summary = {
        "health": {
            "voice_smoke_coverage": 0.40,
            "repeat_fallback_rate": 0.10,
            "mic_unavailable_rate": 0.05,
            "thresholds": {
                "min_voice_smoke_coverage": 0.50,
                "max_repeat_fallback_rate": 0.25,
                "max_mic_unavailable_rate": 0.25,
            },
        }
    }
    signals = build_ops_health_signals(summary)
    assert len(signals) == 3
    assert signals[0].key == "voice_smoke_coverage"
    assert signals[0].comparator == "lt"
    assert signals[0].threshold == 0.50


def test_evaluate_ops_summary_generates_warn_with_breaches() -> None:
    summary = {
        "report_count": 12,
        "health": {
            "voice_smoke_coverage": 0.40,
            "repeat_fallback_rate": 0.30,
            "mic_unavailable_rate": 0.10,
            "thresholds": {
                "min_voice_smoke_coverage": 0.50,
                "max_repeat_fallback_rate": 0.25,
                "max_mic_unavailable_rate": 0.25,
            },
        },
    }
    evaluated = evaluate_ops_summary(summary)
    assert evaluated["status"] == "warn"
    assert evaluated["source"] == "ops_history"
    assert evaluated["metadata"]["report_count"] == 12
    assert len(evaluated["findings"]) >= 1


def test_evaluate_ops_summary_returns_ok_when_healthy() -> None:
    summary = {
        "report_count": 5,
        "health": {
            "voice_smoke_coverage": 0.90,
            "repeat_fallback_rate": 0.05,
            "mic_unavailable_rate": 0.02,
            "thresholds": {
                "min_voice_smoke_coverage": 0.50,
                "max_repeat_fallback_rate": 0.25,
                "max_mic_unavailable_rate": 0.25,
            },
        },
    }
    evaluated = evaluate_ops_summary(summary)
    assert evaluated["status"] == "ok"
    assert evaluated["findings"] == []

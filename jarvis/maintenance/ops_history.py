from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..crsis.defaults import evaluate_ops_snapshot
from ..crsis.engine import persist_snapshot


def list_ops_report_files(report_dir: str = "./logs") -> list[str]:
    """List ops report JSONL files, newest first."""

    base = Path(report_dir)
    if not base.exists():
        return []
    files = [path for path in base.glob("jarvis_ops_report_*.jsonl") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path) for path in files]


def list_ops_alert_files(report_dir: str = "./logs") -> list[str]:
    """List ops alert files (daily JSONL + latest snapshots), newest first."""

    base = Path(report_dir)
    if not base.exists():
        return []

    files = [path for path in base.glob("jarvis_ops_alerts_*.jsonl") if path.is_file()]
    latest_json = base / "jarvis_ops_alerts_latest.json"
    latest_text = base / "jarvis_ops_alerts_latest.txt"
    if latest_json.is_file():
        files.append(latest_json)
    if latest_text.is_file():
        files.append(latest_text)

    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path) for path in files]


def prune_ops_alerts(
    report_dir: str = "./logs", retention_days: int = 30
) -> dict[str, object]:
    """Prune old dated ops-alert JSONL files while keeping latest snapshots."""

    days = max(0, int(retention_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    deleted_files: list[str] = []
    for path_str in list_ops_alert_files(report_dir):
        path = Path(path_str)
        if path.name in {
            "jarvis_ops_alerts_latest.json",
            "jarvis_ops_alerts_latest.txt",
        }:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff_ts:
            path.unlink(missing_ok=True)
            deleted_files.append(str(path))

    remaining = list_ops_alert_files(report_dir)
    return {
        "deleted_count": len(deleted_files),
        "remaining_count": len(remaining),
        "deleted_files": deleted_files,
        "remaining_files": remaining,
    }


def load_ops_reports(
    report_dir: str = "./logs",
    limit: int = 50,
    since_days: int | None = None,
) -> list[dict[str, Any]]:
    """Load up to `limit` latest report entries from JSONL files."""

    remaining = max(0, int(limit))
    if remaining == 0:
        return []
    cutoff = _build_cutoff(since_days)

    reports: list[dict[str, Any]] = []
    for file_path in list_ops_report_files(report_dir):
        if remaining <= 0:
            break
        path = Path(file_path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        # Newest entries in each file are at the bottom.
        for line in reversed(lines):
            if remaining <= 0:
                break
            payload = line.strip()
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                if cutoff is not None and not _is_new_enough(parsed, cutoff):
                    continue
                reports.append(parsed)
                remaining -= 1

    return reports


def summarize_ops_history(
    report_dir: str = "./logs",
    limit: int = 50,
    since_days: int | None = None,
) -> dict[str, Any]:
    """Summarize recent ops runs from persisted report files."""

    reports = load_ops_reports(
        report_dir=report_dir, limit=limit, since_days=since_days
    )
    if not reports:
        return {
            "report_count": 0,
            "limit": int(limit),
            "since_days": None if since_days is None else int(since_days),
            "time_range": {"newest": None, "oldest": None},
            "voice_smoke_runs": 0,
            "voice_fallback_repeat_total": 0,
            "voice_fallback_mic_unavailable_total": 0,
            "tts_backend_counts": {},
            "retention_totals": {
                "memory_deleted": 0,
                "memory_backups_deleted": 0,
                "voice_metrics_deleted": 0,
                "ops_alerts_deleted": 0,
            },
        }

    tts_backend_counts: dict[str, int] = {}
    voice_smoke_runs = 0
    repeat_fallback_total = 0
    mic_unavailable_total = 0
    memory_deleted_total = 0
    memory_backups_deleted_total = 0
    voice_metrics_deleted_total = 0
    ops_alerts_deleted_total = 0

    timestamps: list[str] = []
    for report in reports:
        timestamp = report.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            timestamps.append(timestamp)

        voice_smoke = report.get("voice_smoke")
        if isinstance(voice_smoke, dict):
            voice_smoke_runs += 1
            voice_metrics = voice_smoke.get("voice_metrics", {})
            if isinstance(voice_metrics, dict):
                repeat_fallback_total += _safe_int(
                    voice_metrics.get("fallback_repeat_prompt")
                )
                mic_unavailable_total += _safe_int(
                    voice_metrics.get("fallback_mic_unavailable")
                )
                backend_counts = voice_metrics.get("tts_backend_counts", {})
                if isinstance(backend_counts, dict):
                    for key, value in backend_counts.items():
                        backend = str(key).strip().lower()
                        if not backend:
                            continue
                        tts_backend_counts[backend] = tts_backend_counts.get(
                            backend, 0
                        ) + _safe_int(value)

        retention = report.get("retention", {})
        if isinstance(retention, dict):
            memory_deleted_total += _safe_int(retention.get("memory_deleted"))
            memory_backups_deleted_total += _safe_int(
                retention.get("memory_backups_deleted")
            )
            voice_metrics_deleted_total += _safe_int(
                retention.get("voice_metrics_deleted")
            )
            ops_alerts_deleted_total += _safe_int(retention.get("ops_alerts_deleted"))

    newest = timestamps[0] if timestamps else None
    oldest = timestamps[-1] if timestamps else None
    return {
        "report_count": len(reports),
        "limit": int(limit),
        "since_days": None if since_days is None else int(since_days),
        "time_range": {"newest": newest, "oldest": oldest},
        "voice_smoke_runs": voice_smoke_runs,
        "voice_fallback_repeat_total": repeat_fallback_total,
        "voice_fallback_mic_unavailable_total": mic_unavailable_total,
        "tts_backend_counts": tts_backend_counts,
        "retention_totals": {
            "memory_deleted": memory_deleted_total,
            "memory_backups_deleted": memory_backups_deleted_total,
            "voice_metrics_deleted": voice_metrics_deleted_total,
            "ops_alerts_deleted": ops_alerts_deleted_total,
        },
    }


def evaluate_ops_health(
    summary: dict[str, Any],
    *,
    max_repeat_fallback_rate: float = 0.25,
    max_mic_unavailable_rate: float = 0.25,
    min_voice_smoke_coverage: float = 0.50,
) -> dict[str, Any]:
    """Evaluate summary health against basic operational thresholds."""

    report_count = max(0, _safe_int(summary.get("report_count")))
    voice_smoke_runs = max(0, _safe_int(summary.get("voice_smoke_runs")))
    repeat_total = max(0, _safe_int(summary.get("voice_fallback_repeat_total")))
    mic_total = max(0, _safe_int(summary.get("voice_fallback_mic_unavailable_total")))

    coverage = (voice_smoke_runs / report_count) if report_count > 0 else 0.0
    repeat_rate = (repeat_total / voice_smoke_runs) if voice_smoke_runs > 0 else 0.0
    mic_rate = (mic_total / voice_smoke_runs) if voice_smoke_runs > 0 else 0.0

    issues: list[dict[str, Any]] = []
    if report_count == 0:
        issues.append(
            {
                "severity": "warn",
                "code": "no_reports",
                "message": "No ops reports available.",
            }
        )
    if coverage < float(min_voice_smoke_coverage):
        issues.append(
            {
                "severity": "warn",
                "code": "low_voice_smoke_coverage",
                "message": f"Voice smoke coverage {coverage:.2f} < {float(min_voice_smoke_coverage):.2f}.",
            }
        )

    issues.extend(
        _threshold_issue(
            value=repeat_rate,
            threshold=float(max_repeat_fallback_rate),
            code="repeat_fallback_rate",
            message_label="Repeat fallback rate",
        )
    )
    issues.extend(
        _threshold_issue(
            value=mic_rate,
            threshold=float(max_mic_unavailable_rate),
            code="mic_unavailable_rate",
            message_label="Mic unavailable rate",
        )
    )

    status = "ok"
    if any(issue.get("severity") == "critical" for issue in issues):
        status = "critical"
    elif issues:
        status = "warn"

    return {
        "status": status,
        "voice_smoke_coverage": round(coverage, 4),
        "repeat_fallback_rate": round(repeat_rate, 4),
        "mic_unavailable_rate": round(mic_rate, 4),
        "thresholds": {
            "max_repeat_fallback_rate": float(max_repeat_fallback_rate),
            "max_mic_unavailable_rate": float(max_mic_unavailable_rate),
            "min_voice_smoke_coverage": float(min_voice_smoke_coverage),
        },
        "issues": issues,
    }


def render_ops_summary(summary: dict[str, Any], output_format: str = "json") -> str:
    """Render ops summary as JSON or compact text table."""

    mode = output_format.strip().lower()
    if mode == "json":
        return json.dumps(summary)
    if mode not in {"table", "text"}:
        raise ValueError(f"unsupported_output_format:{output_format}")

    retention = summary.get("retention_totals", {})
    tts_counts = summary.get("tts_backend_counts", {})
    health = summary.get("health", {})
    tts_parts = []
    if isinstance(tts_counts, dict):
        for backend, count in sorted(tts_counts.items()):
            tts_parts.append(f"{backend}:{_safe_int(count)}")
    tts_text = ", ".join(tts_parts) if tts_parts else "none"

    lines = [
        "Jarvis Ops Summary",
        f"reports={_safe_int(summary.get('report_count'))} limit={_safe_int(summary.get('limit'))} since_days={summary.get('since_days')}",
        f"time_newest={summary.get('time_range', {}).get('newest')}",
        f"time_oldest={summary.get('time_range', {}).get('oldest')}",
        (
            "voice "
            f"runs={_safe_int(summary.get('voice_smoke_runs'))} "
            f"fallback_repeat={_safe_int(summary.get('voice_fallback_repeat_total'))} "
            f"fallback_mic={_safe_int(summary.get('voice_fallback_mic_unavailable_total'))} "
            f"tts={tts_text}"
        ),
        (
            "retention "
            f"memory_deleted={_safe_int(retention.get('memory_deleted'))} "
            f"memory_backups_deleted={_safe_int(retention.get('memory_backups_deleted'))} "
            f"voice_metrics_deleted={_safe_int(retention.get('voice_metrics_deleted'))} "
            f"ops_alerts_deleted={_safe_int(retention.get('ops_alerts_deleted'))}"
        ),
    ]
    if isinstance(health, dict) and health:
        lines.append(
            "health "
            f"status={health.get('status')} "
            f"coverage={health.get('voice_smoke_coverage')} "
            f"repeat_rate={health.get('repeat_fallback_rate')} "
            f"mic_rate={health.get('mic_unavailable_rate')}"
        )
        issues = health.get("issues", [])
        if isinstance(issues, list) and issues:
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                lines.append(
                    "issue "
                    f"severity={issue.get('severity')} "
                    f"code={issue.get('code')} "
                    f"message={issue.get('message')}"
                )
    return "\n".join(lines)


def persist_ops_alerts(
    summary: dict[str, Any],
    report_dir: str = "./logs",
    source: str = "ops_history",
) -> dict[str, Any]:
    """Persist warn/critical issues to daily alerts files for triage."""

    base = Path(report_dir)
    base.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    jsonl_path = base / f"jarvis_ops_alerts_{day}.jsonl"
    latest_json_path = base / "jarvis_ops_alerts_latest.json"
    latest_text_path = base / "jarvis_ops_alerts_latest.txt"

    entries = _build_alert_entries(summary=summary, source=source, timestamp=now_iso)
    if entries:
        with jsonl_path.open("a", encoding="utf-8") as file_obj:
            for entry in entries:
                file_obj.write(json.dumps(entry, ensure_ascii=True, default=str) + "\n")

    latest_payload = {
        "timestamp": now_iso,
        "source": source,
        "status": str(summary.get("health", {}).get("status", "ok")).lower()
        if isinstance(summary.get("health"), dict)
        else "ok",
        "issues": entries,
    }
    with latest_json_path.open("w", encoding="utf-8") as file_obj:
        json.dump(latest_payload, file_obj, ensure_ascii=True, indent=2, default=str)

    latest_text = _render_alerts_text(entries)
    with latest_text_path.open("w", encoding="utf-8") as file_obj:
        file_obj.write(latest_text)

    return {
        "written": len(entries),
        "jsonl_path": str(jsonl_path),
        "latest_json_path": str(latest_json_path),
        "latest_text_path": str(latest_text_path),
    }


def evaluate_and_persist_crsis(
    summary: dict[str, Any],
    report_dir: str = "./logs",
    source: str = "ops_history",
) -> dict[str, Any]:
    """Evaluate summary through CRSIS and persist a daily snapshot."""

    snapshot = evaluate_ops_snapshot(summary=summary, source=source)
    files = persist_snapshot(snapshot, log_dir=report_dir)
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
        "files": files,
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _threshold_issue(
    value: float, threshold: float, code: str, message_label: str
) -> list[dict[str, Any]]:
    if value <= threshold:
        return []

    critical_cutoff = min(1.0, threshold * 2.0)
    severity = "critical" if value >= critical_cutoff else "warn"
    return [
        {
            "severity": severity,
            "code": code,
            "message": f"{message_label} {value:.2f} > {threshold:.2f}.",
        }
    ]


def _build_cutoff(since_days: int | None) -> datetime | None:
    if since_days is None:
        return None
    days = max(0, int(since_days))
    return datetime.now(timezone.utc) - timedelta(days=days)


def _is_new_enough(report: dict[str, Any], cutoff: datetime) -> bool:
    timestamp = report.get("timestamp")
    parsed = _parse_iso_utc(timestamp if isinstance(timestamp, str) else "")
    if parsed is None:
        return False
    return parsed >= cutoff


def _parse_iso_utc(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_alert_entries(
    summary: dict[str, Any], source: str, timestamp: str
) -> list[dict[str, Any]]:
    health = summary.get("health", {})
    if not isinstance(health, dict):
        return []
    status = str(health.get("status", "ok")).lower()
    if status not in {"warn", "critical"}:
        return []

    raw_issues = health.get("issues", [])
    issues = raw_issues if isinstance(raw_issues, list) else []
    if not issues:
        return [
            {
                "timestamp": timestamp,
                "source": source,
                "status": status,
                "severity": status,
                "code": "unspecified_issue",
                "message": "Health status is non-ok but no issues were listed.",
            }
        ]

    entries: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        entries.append(
            {
                "timestamp": timestamp,
                "source": source,
                "status": status,
                "severity": str(issue.get("severity", status)),
                "code": str(issue.get("code", "unknown_issue")),
                "message": str(issue.get("message", "")),
            }
        )
    return entries


def _render_alerts_text(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    lines = []
    for entry in entries:
        lines.append(
            f"[{entry.get('severity')}] {entry.get('code')}: {entry.get('message')}"
        )
    return "\n".join(lines)

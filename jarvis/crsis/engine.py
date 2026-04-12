from __future__ import annotations

import json
import operator
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .contracts import CRSISFinding, CRSISSignal, CRSISSnapshot, utc_now_iso


@dataclass
class RuleVersion:
    rule_id: str
    rule_body: dict
    timestamp: str
    change_reason: str


ComparatorFn = Callable[[float, float], bool]

COMPARATORS: dict[str, ComparatorFn] = {
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
}

SEVERITY_RANK = {"ok": 0, "warn": 1, "critical": 2}


class CRSISEngine:
    """Compact rule engine for runtime health signals."""

    def __init__(self, log_dir: str = "./logs"):
        self._rules: dict[str, list[RuleVersion]] = {}
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._rules_file = self._log_dir / "crsis_rules.jsonl"
        self._load_rules()

    def _load_rules(self):
        if not self._rules_file.exists():
            return
        with open(self._rules_file, "r", encoding="utf-8") as f:
            for line in f:
                payload = line.strip()
                if not payload:
                    continue
                try:
                    data = json.loads(payload)
                    v = RuleVersion(
                        rule_id=data["rule_id"],
                        rule_body=data["rule_body"],
                        timestamp=data["timestamp"],
                        change_reason=data["change_reason"],
                    )
                    self._rules.setdefault(v.rule_id, []).append(v)
                except json.JSONDecodeError:
                    continue

    def _persist_rule(self, version: RuleVersion):
        with open(self._rules_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(version)) + "\n")

    def upsert_rule(self, rule_id: str, rule_body: dict, reason: str = "") -> None:
        version = RuleVersion(
            rule_id=rule_id,
            rule_body=rule_body,
            timestamp=datetime.now(timezone.utc).isoformat(),
            change_reason=reason,
        )
        self._rules.setdefault(rule_id, []).append(version)
        self._persist_rule(version)

    def get_rule(self, rule_id: str) -> dict | None:
        versions = self._rules.get(rule_id)
        return versions[-1].rule_body if versions else None

    def rollback(self, rule_id: str, steps: int = 1) -> bool:
        versions = self._rules.get(rule_id)
        if not versions or len(versions) <= steps:
            return False
        self._rules[rule_id] = versions[:-steps]
        # Re-write the entire file to disk to persist rollback state
        # In a real system, we might append a tombstone or rewrite.
        rules_to_write = []
        for r_id, r_versions in self._rules.items():
            rules_to_write.extend(r_versions)
        with open(self._rules_file, "w", encoding="utf-8") as f:
            for v in rules_to_write:
                f.write(json.dumps(asdict(v)) + "\n")
        return True

    def rule_history(self, rule_id: str) -> list[RuleVersion]:
        return list(self._rules.get(rule_id, []))

    def evaluate(
        self,
        signals: list[CRSISSignal],
        source: str = "runtime",
        metadata: dict[str, object] | None = None,
    ) -> CRSISSnapshot:
        findings: list[CRSISFinding] = []
        for signal in signals:
            compare = COMPARATORS.get(signal.comparator)
            if compare is None:
                raise ValueError(f"unsupported_comparator:{signal.comparator}")
            if compare(float(signal.value), float(signal.threshold)):
                findings.append(
                    CRSISFinding(
                        signal_key=signal.key,
                        severity=signal.severity,
                        message=signal.message or _default_message(signal),
                        value=float(signal.value),
                        threshold=float(signal.threshold),
                        comparator=signal.comparator,
                    )
                )
        return CRSISSnapshot(
            timestamp=utc_now_iso(),
            source=source,
            status=_resolve_status(findings),
            signals=tuple(signals),
            findings=tuple(findings),
            metadata=dict(metadata or {}),
        )


def persist_snapshot(
    snapshot: CRSISSnapshot, log_dir: str = "./logs"
) -> dict[str, str]:
    """Persist CRSIS snapshot as daily JSONL and latest JSON files."""

    base = Path(log_dir)
    base.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    jsonl_path = base / f"jarvis_crsis_{day}.jsonl"
    latest_path = base / "jarvis_crsis_latest.json"

    serialized = asdict(snapshot)
    with jsonl_path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(serialized, ensure_ascii=True, default=str) + "\n")

    with latest_path.open("w", encoding="utf-8") as file_obj:
        json.dump(serialized, file_obj, ensure_ascii=True, indent=2, default=str)

    return {"jsonl_path": str(jsonl_path), "latest_path": str(latest_path)}


def read_snapshot_log(
    log_dir: str = "./logs", date_str: str | None = None
) -> list[dict[str, object]]:
    """Load CRSIS snapshots for a given UTC day."""

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path(log_dir) / f"jarvis_crsis_{date_str}.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            payload = line.strip()
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def list_snapshot_files(log_dir: str = "./logs") -> list[str]:
    base = Path(log_dir)
    if not base.exists():
        return []
    files = [path for path in base.glob("jarvis_crsis_*.jsonl") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path) for path in files]


def prune_snapshots(
    log_dir: str = "./logs", retention_days: int = 30
) -> dict[str, object]:
    days = max(0, int(retention_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()
    deleted_files: list[str] = []
    for path_str in list_snapshot_files(log_dir):
        path = Path(path_str)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff_ts:
            path.unlink(missing_ok=True)
            deleted_files.append(str(path))
    remaining_files = list_snapshot_files(log_dir)
    return {
        "deleted_count": len(deleted_files),
        "remaining_count": len(remaining_files),
        "deleted_files": deleted_files,
        "remaining_files": remaining_files,
    }


def _resolve_status(findings: list[CRSISFinding]) -> str:
    if not findings:
        return "ok"
    worst = max(SEVERITY_RANK.get(finding.severity, 1) for finding in findings)
    if worst >= SEVERITY_RANK["critical"]:
        return "critical"
    return "warn"


def _default_message(signal: CRSISSignal) -> str:
    return (
        f"Signal {signal.key} breached comparator {signal.comparator}: "
        f"value={float(signal.value):.4f}, threshold={float(signal.threshold):.4f}."
    )

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Optional
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobStatusSnapshot:
    job_id: str
    state: str
    stage: str
    percent: float
    eta: Optional[str] = None
    last_update: str = field(default_factory=_utc_now)
    errors: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    force_kill_requested: bool = False


@dataclass
class SubscriptionResult:
    turn_id: str
    speaker_id: str
    channel: str
    subscribed: bool


@dataclass
class CancelResult:
    job_id: Optional[str]
    acknowledged: bool
    force: bool


class JobStatusService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._current: Optional[JobStatusSnapshot] = None
        self._subscriptions: list[SubscriptionResult] = []

    def create(self, task: dict) -> JobStatusSnapshot:
        with self._lock:
            job_id = str(task.get("job_id") or f"job-{uuid4().hex[:10]}")
            self._current = JobStatusSnapshot(
                job_id=job_id,
                state="RUNNING",
                stage=task.get("stage", "queued"),
                percent=0.0,
                eta=task.get("eta"),
            )
            return self._current

    def update(self, job_id: str, patch: dict) -> JobStatusSnapshot:
        with self._lock:
            if self._current is None or self._current.job_id != job_id:
                raise ValueError("job_not_found")
            for key, value in patch.items():
                if hasattr(self._current, key):
                    setattr(self._current, key, value)
            self._current.last_update = _utc_now()
            return self._current

    def get_current(self) -> Optional[JobStatusSnapshot]:
        with self._lock:
            return self._current

    def subscribe_on_complete(
        self, turn_id: str, speaker_id: str, channel: str
    ) -> SubscriptionResult:
        with self._lock:
            sub = SubscriptionResult(
                turn_id=turn_id, speaker_id=speaker_id, channel=channel, subscribed=True
            )
            self._subscriptions.append(sub)
            return sub

    def cancel(self, job_id: str, force: bool = False) -> CancelResult:
        with self._lock:
            if self._current is None or self._current.job_id != job_id:
                return CancelResult(job_id=None, acknowledged=False, force=force)
            self._current.cancel_requested = True
            if force:
                self._current.force_kill_requested = True
            self._current.last_update = _utc_now()
            return CancelResult(job_id=job_id, acknowledged=True, force=force)

    def complete(self, job_id: str) -> bool:
        with self._lock:
            if self._current is None or self._current.job_id != job_id:
                return False
            self._current.state = "COMPLETED"
            self._current.percent = 100.0
            self._current.last_update = _utc_now()
            self._current = None
            return True

    def subscription_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    def pop_subscriptions(self) -> list[SubscriptionResult]:
        with self._lock:
            subscriptions = list(self._subscriptions)
            self._subscriptions.clear()
            return subscriptions

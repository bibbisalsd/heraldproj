from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BG1Job:
    job_id: str
    summary: str
    created_at: datetime = field(default_factory=_utc_now)
    idempotency_key: Optional[str] = None


class BG1Queue:
    def __init__(
        self, max_active: int = 1, max_queue: int = 1, ttl_seconds: int = 120
    ) -> None:
        self.max_active = max_active
        self.max_queue = max_queue
        self.ttl_seconds = ttl_seconds
        self.active: Optional[BG1Job] = None
        self.queue: list[BG1Job] = []
        self._seen_keys: dict[str, str] = {}

    def submit(
        self, summary: str, idempotency_key: Optional[str] = None
    ) -> dict[str, str]:
        self._prune_expired()
        if idempotency_key and idempotency_key in self._seen_keys:
            return {
                "accepted": "true",
                "job_id": self._seen_keys[idempotency_key],
                "reason": "deduped",
            }

        if self.active is not None and len(self.queue) >= self.max_queue:
            return {"accepted": "false", "reason": "BG1_BUSY_ACTIVE"}

        job = BG1Job(
            job_id=f"bg1-{uuid4().hex[:10]}",
            summary=summary,
            idempotency_key=idempotency_key,
        )
        if self.active is None:
            self.active = job
            reason = "started"
        else:
            self.queue.append(job)
            reason = "queued"

        if idempotency_key:
            self._seen_keys[idempotency_key] = job.job_id
        return {"accepted": "true", "job_id": job.job_id, "reason": reason}

    def complete_active(self) -> Optional[str]:
        if self.active is None:
            return None
        completed_id = self.active.job_id
        self.active = self.queue.pop(0) if self.queue else None
        return completed_id

    def is_busy(self) -> bool:
        return self.active is not None

    def status(self) -> dict[str, object]:
        self._prune_expired()
        return {
            "active_job_id": self.active.job_id if self.active else None,
            "queue_length": len(self.queue),
            "max_queue_length": self.max_queue,
            "busy": self.is_busy(),
        }

    def _prune_expired(self) -> None:
        cutoff = _utc_now() - timedelta(seconds=self.ttl_seconds)
        self.queue = [job for job in self.queue if job.created_at >= cutoff]

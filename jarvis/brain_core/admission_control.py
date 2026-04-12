from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdmissionResult:
    action: str
    reason_code: str
    accepted: bool


class AdmissionControl:
    def __init__(self, max_active_jobs: int = 1, max_queue_length: int = 1) -> None:
        self.max_active_jobs = max_active_jobs
        self.max_queue_length = max_queue_length

    def evaluate(
        self, decision: str, queue_state: dict, bg1_state: dict
    ) -> AdmissionResult:
        if decision != "bg1":
            return AdmissionResult(
                action="realtime", reason_code="NOT_HEAVY", accepted=True
            )

        active = int(bg1_state.get("active_jobs", 0))
        queued = int(queue_state.get("queue_length", 0))

        if active >= self.max_active_jobs and queued >= self.max_queue_length:
            return AdmissionResult(
                action="reject", reason_code="BG1_BUSY_ACTIVE", accepted=False
            )
        if active >= self.max_active_jobs:
            return AdmissionResult(
                action="queue", reason_code="BG1_QUEUED", accepted=True
            )
        return AdmissionResult(action="run", reason_code="BG1_ACCEPTED", accepted=True)

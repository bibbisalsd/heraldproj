from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
import subprocess
import sys

from .bg1_queue import BG1Queue
from .job_status_service import CancelResult


@dataclass
class BG1RunResult:
    job_id: Optional[str]
    ok: bool
    summary: str


class BG1Worker:
    def __init__(self, queue: BG1Queue) -> None:
        self.queue = queue
        self._active_subprocess: Optional[subprocess.Popen[str]] = None

    def submit_and_run(self, summary: str, fn: Callable[[], str]) -> BG1RunResult:
        submit = self.queue.submit(summary=summary)
        if submit.get("accepted") != "true":
            return BG1RunResult(
                job_id=None, ok=False, summary=submit.get("reason", "rejected")
            )
        try:
            result = fn()
            return BG1RunResult(job_id=submit["job_id"], ok=True, summary=result)
        finally:
            self.queue.complete_active()

    def status(self) -> dict[str, object]:
        return self.queue.status()

    def start_dummy_process(self) -> Optional[int]:
        if (
            self._active_subprocess is not None
            and self._active_subprocess.poll() is None
        ):
            return self._active_subprocess.pid
        self._active_subprocess = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            text=True,
        )
        return self._active_subprocess.pid

    def cancel(self, job_id: str, force: bool = False) -> CancelResult:
        if (
            force
            and self._active_subprocess is not None
            and self._active_subprocess.poll() is None
        ):
            self._active_subprocess.kill()
            return CancelResult(job_id=job_id, acknowledged=True, force=True)
        return CancelResult(job_id=job_id, acknowledged=True, force=force)

from __future__ import annotations
from jarvis.brain_core.bg1_queue import BG1Queue
from jarvis.brain_core.bg1_worker import BG1Worker


def test_force_cancel_kills_active_subprocess():
    worker = BG1Worker(BG1Queue())
    pid = worker.start_dummy_process()
    assert pid is not None
    result = worker.cancel(job_id="job-x", force=True)
    assert result.acknowledged is True
    assert result.force is True

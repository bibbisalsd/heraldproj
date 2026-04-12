from __future__ import annotations
from jarvis.brain_core.bg1_queue import BG1Queue
from jarvis.brain_core.bg1_worker import BG1Worker


def test_bg1_worker_submit_and_run_completes_job():
    queue = BG1Queue(max_active=1, max_queue=1, ttl_seconds=120)
    worker = BG1Worker(queue)
    result = worker.submit_and_run("job", lambda: "done")
    assert result.ok is True
    assert result.summary == "done"
    assert queue.is_busy() is False

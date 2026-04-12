from __future__ import annotations
from jarvis.brain_core.bg1_queue import BG1Queue


def test_bg1_queue_rejects_when_active_and_queue_full():
    queue = BG1Queue(max_active=1, max_queue=1, ttl_seconds=120)
    first = queue.submit("job1")
    second = queue.submit("job2")
    third = queue.submit("job3")

    assert first["accepted"] == "true"
    assert second["accepted"] == "true"
    assert third["accepted"] == "false"
    assert third["reason"] == "BG1_BUSY_ACTIVE"


def test_bg1_queue_supports_idempotency_dedup():
    queue = BG1Queue(max_active=1, max_queue=1, ttl_seconds=120)
    first = queue.submit("job1", idempotency_key="same")
    second = queue.submit("job1", idempotency_key="same")
    assert first["accepted"] == "true"
    assert second["accepted"] == "true"
    assert second["reason"] == "deduped"
    assert second["job_id"] == first["job_id"]

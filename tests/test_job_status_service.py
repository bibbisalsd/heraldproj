from __future__ import annotations
from jarvis.brain_core.job_status_service import JobStatusService


def test_job_status_service_create_update_get():
    svc = JobStatusService()
    snap = svc.create({"stage": "running"})
    assert snap.state == "RUNNING"
    updated = svc.update(snap.job_id, {"percent": 50.0, "stage": "mid"})
    assert updated.percent == 50.0
    current = svc.get_current()
    assert current is not None
    assert current.stage == "mid"


def test_job_status_service_subscribe_and_cancel():
    svc = JobStatusService()
    snap = svc.create({"stage": "running"})
    sub = svc.subscribe_on_complete("t1", "owner", "local")
    assert sub.subscribed is True
    assert svc.subscription_count() == 1
    cancel = svc.cancel(snap.job_id, force=True)
    assert cancel.acknowledged is True
    assert cancel.force is True
    drained = svc.pop_subscriptions()
    assert len(drained) == 1
    assert drained[0].turn_id == "t1"
    assert svc.subscription_count() == 0

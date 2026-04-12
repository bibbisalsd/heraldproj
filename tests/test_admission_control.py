from __future__ import annotations
from jarvis.brain_core.admission_control import AdmissionControl


def test_admission_accepts_non_heavy_to_realtime():
    ac = AdmissionControl()
    result = ac.evaluate("realtime", {"queue_length": 0}, {"active_jobs": 0})
    assert result.accepted is True
    assert result.action == "realtime"


def test_admission_rejects_when_bg1_fully_busy():
    ac = AdmissionControl(max_active_jobs=1, max_queue_length=1)
    result = ac.evaluate("bg1", {"queue_length": 1}, {"active_jobs": 1})
    assert result.accepted is False
    assert result.reason_code == "BG1_BUSY_ACTIVE"

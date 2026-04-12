from __future__ import annotations
from jarvis.brain_core.lane_coordinator import LaneCoordinator


def test_lane_coordinator_classifies_heavy_and_quick_text():
    c = LaneCoordinator()
    heavy = c.classify("research this deeply")
    quick = c.classify("what time is it")
    assert heavy.lane == "bg1"
    assert quick.lane == "realtime"

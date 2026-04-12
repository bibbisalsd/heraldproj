from __future__ import annotations
from jarvis.brain_core.contracts import RawEvent
from jarvis.brain_core.ingress_normalizer import IngressNormalizer
from jarvis.brain_core.lane_coordinator import LaneCoordinator


def test_lane_dispatch_routes_quick_requests_to_realtime():
    normalizer = IngressNormalizer()
    coordinator = LaneCoordinator()
    env = normalizer.normalize(
        RawEvent(source="local_mic", speaker_id="owner", channel="local", payload="what is the time")
    )
    decision = coordinator.route(env, bg1_is_busy=False)
    assert decision.lane == "realtime"


def test_lane_dispatch_routes_heavy_requests_to_bg1():
    normalizer = IngressNormalizer()
    coordinator = LaneCoordinator()
    env = normalizer.normalize(
        RawEvent(source="local_mic", speaker_id="owner", channel="local", payload="research this topic deeply")
    )
    decision = coordinator.route(env, bg1_is_busy=False)
    assert decision.lane == "bg1"
    assert decision.reason == "heavy_request"


def test_lane_dispatch_busy_policy_rejects_new_heavy_job():
    normalizer = IngressNormalizer()
    coordinator = LaneCoordinator()
    env = normalizer.normalize(
        RawEvent(source="local_mic", speaker_id="owner", channel="local", payload="analyze codebase")
    )
    decision = coordinator.route(env, bg1_is_busy=True)
    assert decision.lane == "realtime"
    assert decision.reason == "BG1_BUSY_ACTIVE"

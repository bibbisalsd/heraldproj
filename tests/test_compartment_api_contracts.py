from __future__ import annotations
from jarvis.brain_core.contracts import (
    AddonManifest,
    RawEvent,
    assert_allowed_calls,
    is_call_allowed,
    validate_manifest,
)


def test_manifest_contract_requires_identity_and_summary():
    manifest = AddonManifest(
        addon_id="discord",
        addon_name="Discord Addon",
        version="0.1.0",
        capability_summary="Bridge and channel controls",
    )
    assert validate_manifest(manifest) == []


def test_manifest_contract_flags_missing_capability_summary():
    manifest = AddonManifest(addon_id="x", addon_name="X", version="0.1.0")
    assert "missing_capability_summary" in validate_manifest(manifest)


def test_allowed_call_graph_blocks_hidden_coupling():
    assert is_call_allowed("ingress_hub", "ingress_normalizer")
    blocked = assert_allowed_calls(
        [("realtime_lane", "memory_service"), ("addon_manager", "brain")]
    )
    assert ("realtime_lane", "memory_service") in blocked
    assert ("addon_manager", "brain") in blocked


def test_raw_event_minimum_shape():
    event = RawEvent(
        source="local_mic",
        speaker_id="owner",
        channel="local",
        payload="status",
    )
    assert event.source == "local_mic"
    assert event.payload == "status"

from __future__ import annotations
from jarvis.brain_core.contracts import RawEvent
from jarvis.brain_core.ingress_normalizer import IngressNormalizer


def test_ingress_normalizer_maps_local_mic_to_owner_profile():
    normalizer = IngressNormalizer()
    env = normalizer.normalize(
        RawEvent(source="local_mic", speaker_id="owner", channel="local", payload="status")
    )
    assert env.profile == "owner"
    assert env.text == "status"

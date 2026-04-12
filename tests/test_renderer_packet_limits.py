from __future__ import annotations
from jarvis.brain_core.response_compiler import ResponseCompiler


def test_renderer_packet_limit_observed():
    compiler = ResponseCompiler(max_packet_tokens=8)
    from jarvis.brain_core.contracts import EvidencePacket, VerifiedFact
    evidence_packet = EvidencePacket(
        latest_user_message="a b c d e f g h i j",
        resolved_intent="test",
        verified_facts=[VerifiedFact(content="verified fact one two three four five", source="brain", confidence=1.0, timestamp="", verification_strength="observed")]
    )
    packet = compiler.compile(evidence_packet=evidence_packet)
    if packet.overflowed:
        assert len(packet.facts) >= 1

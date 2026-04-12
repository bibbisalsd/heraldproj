from __future__ import annotations
from jarvis.brain_core.response_compiler import ResponseCompiler


from jarvis.brain_core.contracts import EvidencePacket

def test_response_compiler_keeps_conversation_context():
    compiler = ResponseCompiler(max_packet_tokens=384)
    packet = compiler.compile(
        evidence_packet=EvidencePacket(
            latest_user_message="status",
            resolved_intent="test",
        ),
        conversation_items=[
            "user:hello | intent:greeting | assistant:Hello. I am ready.",
            "user:what time is it | intent:time_query | assistant:It is 10:00.",
        ],
    )

    assert len(packet.conversation_context) == 2
    assert "intent:greeting" in packet.conversation_context[0]

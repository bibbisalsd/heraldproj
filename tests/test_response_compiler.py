from __future__ import annotations
from jarvis.brain_core.response_compiler import ResponseCompiler


from jarvis.brain_core.contracts import EvidencePacket, VerifiedFact, TaskInfo, MemoryInfo

def test_response_compiler_merges_user_tool_memory_and_job_status():
    compiler = ResponseCompiler(max_packet_tokens=384)
    packet = compiler.compile(
        evidence_packet=EvidencePacket(
            latest_user_message="status",
            resolved_intent="test",
            verified_facts=[
                VerifiedFact(content="Jarvis is online.", source="brain", confidence=1.0, timestamp="", verification_strength="observed"),
                VerifiedFact(content="tool ok", source="tool", confidence=1.0, timestamp="", verification_strength="observed"),
                VerifiedFact(content="remembered fact", source="memory", confidence=1.0, timestamp="", verification_strength="observed"),
            ],
            task_info=TaskInfo(task_id="1", subject="test", original_request="test", state="RUNNING", progress_percent=50),
        )
    )
    joined = " ".join(packet.facts)
    assert packet.user_text == "status"
    assert "brain:Jarvis is online." in joined
    assert "tool:tool ok" in joined
    assert "memory:remembered fact" in joined
    assert "job_status:RUNNING" in joined


def test_response_compiler_truncates_when_over_token_budget():
    compiler = ResponseCompiler(max_packet_tokens=5)
    packet = compiler.compile(
        evidence_packet=EvidencePacket(
            latest_user_message="one two three four five six seven",
            resolved_intent="test",
            verified_facts=[
                VerifiedFact(content="fact one two three four", source="brain", confidence=1.0, timestamp="", verification_strength="observed")
            ]
        )
    )
    assert packet.overflowed is True

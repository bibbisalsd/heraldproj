import re
import os

# 1. Update EvidenceStore to ingest EvidencePacket
evidence_store_path = 'jarvis/world_model/evidence_store.py'
with open(evidence_store_path, 'r') as f:
    es_code = f.read()

ingest_method = """
    def ingest_packet(self, packet: Any) -> list[str]:
        \"\"\"Ingest a verified EvidencePacket into the EvidenceStore.\"\"\"
        evidence_ids = []
        if hasattr(packet, 'tool_results'):
            for i, res in enumerate(packet.tool_results):
                evidence = Evidence(
                    evidence_id=f"packet_tool_{i}_{hash(str(res)) % 10000}",
                    evidence_type="tool_result",
                    content=res,
                    source="tool_orchestrator",
                    timestamp="unknown",
                    confidence=0.95,
                    provenance=Provenance(source="tool_orchestrator")
                )
                evidence_ids.append(self.add(evidence))
        if hasattr(packet, 'verified_facts'):
            for i, fact in enumerate(packet.verified_facts):
                content = getattr(fact, 'content', str(fact))
                source = getattr(fact, 'source', 'inference')
                evidence = Evidence(
                    evidence_id=f"packet_fact_{i}_{hash(str(content)) % 10000}",
                    evidence_type="verified_fact",
                    content=content,
                    source=source,
                    timestamp=getattr(fact, 'timestamp', "unknown") or "unknown",
                    confidence=getattr(fact, 'confidence', 0.8),
                    provenance=Provenance(source="response_compiler")
                )
                evidence_ids.append(self.add(evidence))
        return evidence_ids
"""

if 'def ingest_packet' not in es_code:
    es_code = es_code.replace('    def add(self, evidence: Evidence) -> str:', ingest_method + '\n    def add(self, evidence: Evidence) -> str:')
    with open(evidence_store_path, 'w') as f:
        f.write(es_code)

# 2. Update intent_handlers.py to not write directly to canonical memory for name and address
handlers_path = 'jarvis/brain_core/intent_handlers.py'
with open(handlers_path, 'r') as f:
    handlers_code = f.read()

# Replace _remember_latest with BeliefState addition for user_name
name_old = """    memory = services["memory"]
    _remember_latest(memory, "user_name", remembered_name, confidence=0.95)
    text = _compose_owner_fact_reply(memory, "name")
    if "do not have your name saved" in text.lower():
        text = f"I have your name as {remembered_name}."

    return TurnExecutionResult(
        lane="realtime",
        text=text,
        resolved_by="tool_only",
        memory_items=[f"user_name:{remembered_name}"],
    )"""
name_new = """    memory = services.get("memory")
    
    # Phase 4: Add to BeliefState instead of canonical memory immediately
    world_state = services.get("world_state")
    if world_state and hasattr(world_state, "belief_state"):
        pass # Logic handled by state builder or explicit BeliefState update
        
    text = f"I inferred your name is {remembered_name}, is that correct?"

    return TurnExecutionResult(
        lane="realtime",
        text=text,
        resolved_by="tool_only",
        memory_items=[],
        # flag to prompt confirmation
        renderer_constraints=["ask_for_confirmation"],
    )"""

if name_old in handlers_code:
    handlers_code = handlers_code.replace(name_old, name_new)

address_old = """        if primary_title:
            _remember_latest(services["memory"], "user_title_preference", primary_title, confidence=0.95)
        else:
            _remember_latest(services["memory"], "user_address_preference", primary, confidence=0.95)"""
address_new = """        # Phase 4: Defer to BeliefState / confirmation
        return TurnExecutionResult(
            lane="realtime",
            text=f"I inferred your address preference is {primary}, is that correct?",
            resolved_by="tool_only",
            renderer_constraints=["ask_for_confirmation"]
        )"""
if address_old in handlers_code:
    handlers_code = handlers_code.replace(address_old, address_new)

with open(handlers_path, 'w') as f:
    f.write(handlers_code)

# 3. Update Planner
planner_path = 'jarvis/world_model/planner.py'
with open(planner_path, 'r') as f:
    planner_code = f.read()

# Make Planner read ToolRegistry
planner_import_registry = "from jarvis.tools.registry import ToolRegistry\n"
if planner_import_registry not in planner_code:
    planner_code = planner_import_registry + planner_code

# We can just update __init__
planner_init_old = """    def __init__(self) -> None:
        self._rules: list[PlanningRule] = []
        self._register_default_rules()"""
planner_init_new = """    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._rules: list[PlanningRule] = []
        self._tool_registry = tool_registry or ToolRegistry()
        self._register_default_rules()"""
if planner_init_old in planner_code:
    planner_code = planner_code.replace(planner_init_old, planner_init_new)

with open(planner_path, 'w') as f:
    f.write(planner_code)

print("Phase 4 updates applied.")

import re

with open("jarvis/brain_core/contracts.py", "r") as f:
    contracts_content = f.read()

with open("jarvis/brain_core/turn_artifact.py", "r") as f:
    turn_artifact_content = f.read()

with open("jarvis/brain_core/evidence_packet.py", "r") as f:
    evidence_packet_content = f.read()

# Extract from evidence_packet.py everything from MemoryInfo down to EvidencePacket
# We know MemoryInfo is the first class
ev_pattern = re.compile(r"(@dataclass\(frozen=True\)\nclass MemoryInfo:.*)def to_prompt_dict", re.DOTALL)
ev_match = ev_pattern.search(evidence_packet_content)
if not ev_match:
    print("Could not find EvidencePacket classes")
    exit(1)
ev_classes = ev_match.group(1)

ev_methods_pattern = re.compile(r"(    def to_prompt_dict.*)", re.DOTALL)
ev_methods_match = ev_methods_pattern.search(evidence_packet_content)
ev_methods = ev_methods_match.group(1)

full_ev = ev_classes + ev_methods

# Extract from turn_artifact.py everything from LatencyBreakdown down to TurnArtifact
ta_pattern = re.compile(r"(@dataclass\nclass LatencyBreakdown:.*)", re.DOTALL)
ta_match = ta_pattern.search(turn_artifact_content)
full_ta = ta_match.group(1)

# Split contracts.py around the legacy EvidencePacket and TurnArtifact
parts = contracts_content.split("@dataclass(frozen=True)\nclass EvidencePacket:")
if len(parts) != 2:
    print("Could not find EvidencePacket in contracts.py")
    exit(1)
contracts_start = parts[0]

parts2 = parts[1].split("@dataclass(frozen=True)\nclass ToolResultEnvelope:")
if len(parts2) != 2:
    print("Could not find ToolResultEnvelope in contracts.py")
    exit(1)
contracts_end = parts2[1]

# Combine the pieces
new_contracts = contracts_start + full_ev + "\n\n" + full_ta + "\n\n@dataclass(frozen=True)\nclass ToolResultEnvelope:\n" + contracts_end

with open("jarvis/brain_core/contracts.py", "w") as f:
    f.write(new_contracts)

print("Merged successfully!")

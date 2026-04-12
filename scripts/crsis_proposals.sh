#!/usr/bin/env bash
# CRSIS Proposals CLI - Review and manage improvement proposals
# Usage: ./scripts/crsis_proposals.sh <command> [args]
#
# Commands:
#   list              - Show pending proposals
#   show <id>         - Display proposal details with evidence
#   approve <id>      - Approve proposal for application
#   reject <id> <msg> - Reject with reason
#   apply <id>        - Apply an approved proposal
#   stats             - Show proposal statistics

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROPOSALS_DIR="$PROJECT_ROOT/.crsis/proposals"

# Ensure proposals directory exists
if [ ! -d "$PROPOSALS_DIR" ]; then
    echo "No proposals directory found. Run CRSIS first?"
    exit 1
fi

COMMAND="${1:-list}"
PROPOSAL_ID="${2:-}"
REASON="${3:-}"

cd "$PROJECT_ROOT"

case "$COMMAND" in
    list)
        python3 << 'PYEOF'
import json
from pathlib import Path

proposals_dir = Path(".crsis/proposals")
pending = []

for f in proposals_dir.glob("*.json"):
    data = json.loads(f.read_text())
    if data.get("status") == "pending":
        pending.append(data)

if not pending:
    print("No pending proposals.")
else:
    print("\n\033[36mPending Proposals:\033[0m")
    print("------------------")
    for p in sorted(pending, key=lambda x: x.get("created_at", ""), reverse=True):
        evidence = p.get("evidence", [])
        confidence = evidence[0].get("confidence", 0) if evidence else 0
        print(f"\n\033[33m[{p['proposal_id']}]\033[0m")
        print(f"  Type: {p['proposal_type']}")
        print(f"  Target: {p['target_file']}")
        print(f"  Impact: {p['expected_impact']}")
        print(f"  Evidence: {len(evidence)} findings, confidence: {confidence:.2f}")
PYEOF
        ;;

    show)
        if [ -z "$PROPOSAL_ID" ]; then
            echo "Usage: crsis_proposals.sh show <proposal_id>"
            exit 1
        fi
        python3 << PYEOF
import json
from pathlib import Path

proposal_file = Path(".crsis/proposals/$PROPOSAL_ID.json")
if not proposal_file.exists():
    print(f"\033[31mProposal not found: $PROPOSAL_ID\033[0m")
    exit(1)

data = json.loads(proposal_file.read_text())

print("\n\033[36m========================================\033[0m")
print(f"\033[36mProposal: {data['proposal_id']}\033[0m")
print("\033[36m========================================\033[0m\n")

print(f"Type:           {data['proposal_type']}")
print(f"Target File:    {data['target_file']}")
print(f"Target:         {data['target_structure']}")
status_color = 33 if data['status'] == 'pending' else (32 if data['status'] == 'approved' else 31)
print(f"Status:         \033[{status_color}m{data['status']}\033[0m")
print(f"Created:        {data['created_at']}")

print("\nExpected Impact:")
print(f"  \033[90m{data['expected_impact']}\033[0m")

print("\nProposed Change:")
change = data.get('proposed_change', {})
for k, v in change.items():
    print(f"  {k}: {v}")

print(f"\nEvidence ({len(data.get('evidence', []))} findings):")
for e in data.get('evidence', []):
    print(f"  - Type: {e.get('pattern_type', 'unknown')}")
    print(f"    Component: {e.get('affected_component', 'unknown')}")
    print(f"    Confidence: {e.get('confidence', 0):.2f}")
    examples = e.get('examples', [])
    if examples:
        print(f"    Examples: {', '.join(examples)}")

print("\nRollback Path:")
print(f"  \033[90m{data['rollback_path']}\033[0m")
PYEOF
        ;;

    approve)
        if [ -z "$PROPOSAL_ID" ]; then
            echo "Usage: crsis_proposals.sh approve <proposal_id>"
            exit 1
        fi
        python3 << PYEOF
import json
from pathlib import Path
from datetime import datetime, timezone

proposal_file = Path(".crsis/proposals/$PROPOSAL_ID.json")
if not proposal_file.exists():
    print(f"\033[31mProposal not found: $PROPOSAL_ID\033[0m")
    exit(1)

data = json.loads(proposal_file.read_text())
data['status'] = 'approved'
data['approved_by'] = 'user'
data['approved_at'] = datetime.now(timezone.utc).isoformat()

proposal_file.write_text(json.dumps(data, indent=2))
print(f"\033[32mProposal approved: $PROPOSAL_ID\033[0m")
PYEOF
        ;;

    reject)
        if [ -z "$PROPOSAL_ID" ]; then
            echo "Usage: crsis_proposals.sh reject <proposal_id> [reason]"
            exit 1
        fi
        python3 << PYEOF
import json
from pathlib import Path
from datetime import datetime, timezone

proposal_file = Path(".crsis/proposals/$PROPOSAL_ID.json")
if not proposal_file.exists():
    print(f"\033[31mProposal not found: $PROPOSAL_ID\033[0m")
    exit(1)

data = json.loads(proposal_file.read_text())
data['status'] = 'rejected'
data['rejected_by'] = 'user'
data['rejected_reason'] = "$REASON"
data['rejected_at'] = datetime.now(timezone.utc).isoformat()

proposal_file.write_text(json.dumps(data, indent=2))
print(f"\033[33mProposal rejected: $PROPOSAL_ID ($REASON)\033[0m")
PYEOF
        ;;

    apply)
        if [ -z "$PROPOSAL_ID" ]; then
            echo "Usage: crsis_proposals.sh apply <proposal_id>"
            exit 1
        fi
        python3 << PYEOF
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, '.')

from jarvis.crsis.contracts import CRSISProposal
from jarvis.crsis.applier import ChangeApplier
from jarvis.crsis.api import ProposalAPI

proposal_file = Path(".crsis/proposals/$PROPOSAL_ID.json")
if not proposal_file.exists():
    print(f"\033[31mProposal not found: $PROPOSAL_ID\033[0m")
    exit(1)

data = json.loads(proposal_file.read_text())

if data['status'] != 'approved':
    print(f"\033[31mProposal must be approved first. Current status: {data['status']}\033[0m")
    exit(1)

# Reconstruct evidence list
evidence_list = []
for e in data.get('evidence', []):
    from jarvis.crsis.contracts import PatternFinding
    evidence_list.append(PatternFinding(
        pattern_type=e.get('pattern_type', ''),
        affected_component=e.get('affected_component', ''),
        evidence_count=e.get('evidence_count', 0),
        confidence=e.get('confidence', 0),
        examples=e.get('examples', []),
        time_range=tuple(e.get('time_range', ['', ''])),
    ))

proposal = CRSISProposal(
    proposal_id=data['proposal_id'],
    proposal_type=data['proposal_type'],
    target_file=data['target_file'],
    target_structure=data['target_structure'],
    proposed_change=data['proposed_change'],
    evidence=evidence_list,
    expected_impact=data['expected_impact'],
    rollback_path=data['rollback_path'],
    created_at=data.get('created_at', ''),
)
proposal.status = 'approved'

print("\033[36mApplying proposal...\033[0m")

applier = ChangeApplier('.')
result = applier.apply(proposal)

if result.success:
    print("\033[32mSUCCESS\033[0m")
    print(f"Backup: {result.backup_path}")

    # Update status
    data['status'] = 'applied'
    from datetime import datetime, timezone
    data['applied_at'] = datetime.now(timezone.utc).isoformat()
    proposal_file.write_text(json.dumps(data, indent=2))
else:
    print("\033[31mFAILED\033[0m")
    print(f"Error: {result.error}")
    print(f"Rolled back: {result.rolled_back}")
PYEOF
        ;;

    stats)
        python3 << 'PYEOF'
import json
from pathlib import Path

proposals_dir = Path(".crsis/proposals")
stats = {"pending": 0, "approved": 0, "rejected": 0, "applied": 0, "rolled_back": 0}

for f in proposals_dir.glob("*.json"):
    data = json.loads(f.read_text())
    status = data.get("status", "pending")
    if status in stats:
        stats[status] += 1

print("\n\033[36mCRSIS Proposal Statistics\033[0m")
print("========================\n")
print(f"Pending:     \033[33m{stats['pending']}\033[0m")
print(f"Approved:    \033[32m{stats['approved']}\033[0m")
print(f"Rejected:    \033[31m{stats['rejected']}\033[0m")
print(f"Applied:     \033[32m{stats['applied']}\033[0m")
print(f"Rolled back: \033[35m{stats['rolled_back']}\033[0m")
print("")
PYEOF
        ;;

    *)
        echo ""
        echo -e "\033[36mCRSIS Proposals CLI\033[0m"
        echo ""
        echo "Usage: ./scripts/crsis_proposals.sh <command> [args]"
        echo ""
        echo "Commands:"
        echo "  list              - Show pending proposals"
        echo "  show <id>         - Display proposal details"
        echo "  approve <id>      - Approve proposal"
        echo "  reject <id> <msg> - Reject with reason"
        echo "  apply <id>        - Apply approved proposal"
        echo "  stats             - Show statistics"
        ;;
esac

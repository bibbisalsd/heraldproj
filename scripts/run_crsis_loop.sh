#!/usr/bin/env bash
# CRSIS Loop Runner - Manual trigger for CRSIS self-improvement loop
# Usage: ./scripts/run_crsis_loop.sh [options]
#
# Options:
#   --analysis-window <int>   Hours of logs to analyze (default: 24)
#   --auto-apply <float>      Confidence threshold for auto-apply (default: 0.95)
#   --dry-run                 Generate proposals without applying
#   --no-approval             Skip approval requirement

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
ANALYSIS_WINDOW=24
AUTO_APPLY=0.95
DRY_RUN="False"
NO_APPROVAL="False"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --analysis-window)
            ANALYSIS_WINDOW="$2"
            shift 2
            ;;
        --auto-apply)
            AUTO_APPLY="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="True"
            shift
            ;;
        --no-approval)
            NO_APPROVAL="True"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo ""
echo -e "\033[36m========================================\033[0m"
echo -e "\033[36mCRSIS Self-Improvement Loop\033[0m"
echo -e "\033[36m========================================\033[0m"
echo ""
echo "Configuration:"
echo "  Analysis Window:    $ANALYSIS_WINDOW hours"
echo "  Auto-Apply Threshold: $AUTO_APPLY"
echo "  Dry Run:            $DRY_RUN"
echo "  Require Approval:   $([ "$NO_APPROVAL" = "True" ] && echo "No" || echo "Yes")"
echo ""

cd "$PROJECT_ROOT"

# Check for libcst and handle accordingly
LIBCST_AVAILABLE=$(python3 -c "import libcst; print('yes')" 2>/dev/null || echo "no")

if [ "$LIBCST_AVAILABLE" = "no" ] && [ "$DRY_RUN" = "False" ]; then
    echo -e "\033[31mError: libcst not installed. Install with: pip install libcst\033[0m"
    echo -e "\033[33mFor analysis-only mode, add --dry-run flag.\033[0m"
    exit 1
fi

python3 << EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')

print("Step 1: Analyzing event logs...")
from jarvis.crsis.analyzer import DecisionLogAnalyzer
from jarvis.observability.events import PersistentEventLogger

event_log = PersistentEventLogger(log_dir='$PROJECT_ROOT/logs')
analyzer = DecisionLogAnalyzer(event_log)
patterns = analyzer.analyze_last_n_hours($ANALYSIS_WINDOW)
print(f"  Found {len(patterns)} patterns")

for pattern in patterns:
    print(f"    - {pattern.pattern_type}: {pattern.affected_component} (confidence: {pattern.confidence:.2f})")

print("\nStep 2: Generating proposals...")
from jarvis.crsis.proposer import ProposalGenerator
proposer = ProposalGenerator()
proposals = proposer.generate_proposals(patterns)
print(f"  Generated {len(proposals)} proposals")

for p in proposals:
    print(f"    - [{p.proposal_id}] {p.proposal_type} -> {p.target_file}")

# Only run full loop if libcst is available
if "$LIBCST_AVAILABLE" == "yes":
    print("\nStep 3: Running full loop...")
    from jarvis.maintenance.crsis_automation import CRSISAutomation, CRSISLoopConfig

    config = CRSISLoopConfig(
        analysis_window_hours=$ANALYSIS_WINDOW,
        auto_apply_threshold=$AUTO_APPLY,
        dry_run=$DRY_RUN,
        require_approval=$([ "$NO_APPROVAL" = "True" ] && echo "False" || echo "True"),
    )

    automation = CRSISAutomation(project_root='$PROJECT_ROOT')
    result = automation.run_loop(config)

    print(f"\n\033[36m========================================\033[0m")
    print(f"\033[36mCRSIS Loop Result\033[0m")
    print(f"\033[36m========================================\033[0m")
    print(f"Patterns detected:    {result.patterns_detected}")
    print(f"Proposals generated:  {result.proposals_generated}")
    print(f"Auto-applied:         {result.auto_applied}")
    print(f"Applied successfully: {result.applied_successfully}")
    print(f"Rolled back:          {result.rolled_back}")

    if not result.proposals_generated:
        print("\nNo proposals generated. System operating normally.")
    elif result.applied_successfully > 0:
        print("\nReview applied changes with: ./scripts/crsis_proposals.sh stats")
    else:
        print("\nReview pending proposals with: ./scripts/crsis_proposals.sh list")
else:
    print("\n\033[33m[Full loop skipped - install libcst to apply changes]\033[0m")
    if proposals:
        print("\nReview proposals with: ./scripts/crsis_proposals.sh list")
EOF

echo ""
echo -e "\033[36m========================================\033[0m"

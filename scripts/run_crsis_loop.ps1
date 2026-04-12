# CRSIS Loop Runner - Manual trigger for CRSIS self-improvement loop
# Usage: .\scripts\run_crsis_loop.ps1 [options]
#
# Options:
#   -AnalysisWindowHours <int>  Hours of logs to analyze (default: 24)
#   -AutoApplyThreshold <float>  Confidence threshold for auto-apply (default: 0.95)
#   -DryRun                     Generate proposals without applying
#   -NoApproval                 Skip approval requirement (auto-apply high-confidence)

param(
    [int]$AnalysisWindowHours = 24,
    [double]$AutoApplyThreshold = 0.95,
    [switch]$DryRun,
    [switch]$NoApproval
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir/.."

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "CRSIS Self-Improvement Loop" -ForegroundColor Cyan
Write-Host "========================================`n"

Write-Host "Configuration:"
Write-Host "  Analysis Window:    $AnalysisWindowHours hours"
Write-Host "  Auto-Apply Threshold: $AutoApplyThreshold"
Write-Host "  Dry Run:            $($DryRun ? 'Yes' : 'No')"
Write-Host "  Require Approval:   $($NoApproval ? 'No' : 'Yes')"
Write-Host ""

# Run CRSIS loop via Python
$pythonScript = @"
import sys
sys.path.insert(0, '$ProjectRoot')

from jarvis.maintenance.crsis_automation import CRSISAutomation, CRSISLoopConfig

config = CRSISLoopConfig(
    analysis_window_hours=$AnalysisWindowHours,
    auto_apply_threshold=$AutoApplyThreshold,
    dry_run=$($DryRun ? 'True' : 'False'),
    require_approval=$($NoApproval ? 'False' : 'True'),
)

automation = CRSISAutomation(project_root='$ProjectRoot')

print("Step 1: Analyzing event logs...")
patterns = automation.analyze_only($AnalysisWindowHours)
print(f"  Found {len(patterns)} patterns")

for pattern in patterns:
    print(f"    - {pattern.pattern_type}: {pattern.affected_component} (confidence: {pattern.confidence})")

print("\\nStep 2: Generating proposals...")
from jarvis.crsis.proposer import ProposalGenerator
proposer = ProposalGenerator()
proposals = proposer.generate_proposals(patterns)
print(f"  Generated {len(proposals)} proposals")

for p in proposals:
    print(f"    - [{p.proposal_id}] {p.proposal_type} -> {p.target_file}")

print("\\nStep 3: Running full loop...")
result = automation.run_loop(config)

print(f"\\n========================================")
print(f"CRSIS Loop Result")
print(f"========================================")
print(f"Patterns detected:    {result.patterns_detected}")
print(f"Proposals generated:  {result.proposals_generated}")
print(f"Auto-applied:         {result.auto_applied}")
print(f"Applied successfully: {result.applied_successfully}")
print(f"Rolled back:          {result.rolled_back}")

if not result.proposals_generated:
    print("\\nNo proposals generated. System operating normally.")
elif result.applied_successfully > 0:
    print("\\nReview applied changes with: .\\scripts\\crsis_proposals.ps1 stats")
else:
    print("\\nReview pending proposals with: .\\scripts\\crsis_proposals.ps1 list")
"@

python -c $pythonScript 2>&1

Write-Host "`n========================================`n" -ForegroundColor Cyan

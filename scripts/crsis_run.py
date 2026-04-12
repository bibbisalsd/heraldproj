#!/usr/bin/env python3
"""CRSIS automation runner - analyze logs and generate improvement proposals."""

from jarvis.maintenance.crsis_automation import CRSISAutomation, CRSISLoopConfig


def main():
    print("=== CRSIS Self-Improvement Analysis ===\n")

    # Initialize automation
    automation = CRSISAutomation()

    # Run analysis (dry run = no auto-apply)
    config = CRSISLoopConfig(
        analysis_window_hours=24,
        dry_run=True,
        require_approval=True,
    )

    result = automation.run_loop(config)

    print(f"Patterns detected:     {result.patterns_detected}")
    print(f"Proposals generated:   {result.proposals_generated}")
    print(f"Auto-applied:          {result.auto_applied}")
    print(f"Applied successfully:  {result.applied_successfully}")
    print(f"Rolled back:           {result.rolled_back}")

    # Show pending proposals
    pending = automation.list_pending_proposals()
    if pending:
        print(f"\n=== Pending Proposals ({len(pending)}) ===")
        for p in pending:
            print(f"  - {p['proposal_id']}: {p.get('description', 'N/A')} [{p['status']}]")
    else:
        print("\nNo pending proposals.")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()

# CRSIS Proposals CLI - Review and manage improvement proposals
# Usage: .\scripts\crsis_proposals.ps1 <command> [args]
#
# Commands:
#   list              - Show pending proposals
#   show <id>         - Display proposal details with evidence
#   approve <id>      - Approve proposal for application
#   reject <id> <msg> - Reject with reason
#   apply <id>        - Apply an approved proposal
#   stats             - Show proposal statistics

param(
    [Parameter(Position = 0)]
    [string]$Command = "list",

    [Parameter(Position = 1)]
    [string]$ProposalId,

    [Parameter(Position = 2)]
    [string]$Reason
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir/.."
$ProposalsDir = "$ProjectRoot/.crsis/proposals"

# Ensure proposals directory exists
if (-not (Test-Path $ProposalsDir)) {
    Write-Host "No proposals directory found. Running CRSIS first?"
    exit 1
}

function Get-PendingProposals {
    Get-ChildItem "$ProposalsDir/*.json" | ForEach-Object {
        $content = Get-Content $_.FullName -Raw | ConvertFrom-Json
        if ($content.status -eq "pending") {
            $content
        }
    }
}

function Show-Proposal {
    param([string]$Id)

    $file = Get-Item "$ProposalsDir/$Id.json" -ErrorAction SilentlyContinue
    if (-not $file) {
        Write-Host "Proposal not found: $Id" -ForegroundColor Red
        return
    }

    $proposal = Get-Content $file.FullName -Raw | ConvertFrom-Json

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "Proposal: $($proposal.proposal_id)" -ForegroundColor Cyan
    Write-Host "========================================`n"

    Write-Host "Type:           $($proposal.proposal_type)"
    Write-Host "Target File:    $($proposal.target_file)"
    Write-Host "Target:         $($proposal.target_structure)"
    Write-Host "Status:         $($proposal.status)" -ForegroundColor $(if ($proposal.status -eq "pending") { "Yellow" } elseif ($proposal.status -eq "approved") { "Green" } else { "Red" })
    Write-Host "Created:        $($proposal.created_at)"
    Write-Host "`nExpected Impact:"
    Write-Host "  $($proposal.expected_impact)" -ForegroundColor Gray
    Write-Host "`nProposed Change:"
    $proposal.proposed_change | ConvertTo-Json -Depth 5 | ForEach-Object { Write-Host "  $_" }

    Write-Host "`nEvidence ($($proposal.evidence.Count) findings):"
    foreach ($e in $proposal.evidence) {
        Write-Host "  - Type: $($e.pattern_type)"
        Write-Host "    Component: $($e.affected_component)"
        Write-Host "    Confidence: $($e.confidence)"
        Write-Host "    Examples: $($e.examples -join ', ')"
    }

    Write-Host "`nRollback Path:"
    Write-Host "  $($proposal.rollback_path)" -ForegroundColor Gray
}

function Approve-Proposal {
    param([string]$Id)

    $file = Get-Item "$ProposalsDir/$Id.json" -ErrorAction SilentlyContinue
    if (-not $file) {
        Write-Host "Proposal not found: $Id" -ForegroundColor Red
        return
    }

    $proposal = Get-Content $file.FullName -Raw | ConvertFrom-Json
    $proposal.status = "approved"
    $proposal.approved_by = "user"
    $proposal.approved_at = (Get-Date -Format "o")

    $proposal | ConvertTo-Json -Depth 10 | Set-Content $file.FullName
    Write-Host "Proposal approved: $Id" -ForegroundColor Green
}

function Reject-Proposal {
    param(
        [string]$Id,
        [string]$Reason
    )

    $file = Get-Item "$ProposalsDir/$Id.json" -ErrorAction SilentlyContinue
    if (-not $file) {
        Write-Host "Proposal not found: $Id" -ForegroundColor Red
        return
    }

    $proposal = Get-Content $file.FullName -Raw | ConvertFrom-Json
    $proposal.status = "rejected"
    $proposal.rejected_by = "user"
    $proposal.rejected_reason = $Reason
    $proposal.rejected_at = (Get-Date -Format "o")

    $proposal | ConvertTo-Json -Depth 10 | Set-Content $file.FullName
    Write-Host "Proposal rejected: $Id ($Reason)" -ForegroundColor Yellow
}

function Apply-Proposal {
    param([string]$Id)

    $file = Get-Item "$ProposalsDir/$Id.json" -ErrorAction SilentlyContinue
    if (-not $file) {
        Write-Host "Proposal not found: $Id" -ForegroundColor Red
        return
    }

    $proposal = Get-Content $file.FullName -Raw | ConvertFrom-Json

    if ($proposal.status -ne "approved") {
        Write-Host "Proposal must be approved first. Current status: $($proposal.status)" -ForegroundColor Red
        return
    }

    # Apply the change using Python
    Write-Host "Applying proposal..." -ForegroundColor Cyan

    $pythonScript = @"
import sys
sys.path.insert(0, '$ProjectRoot')

from jarvis.crsis.contracts import CRSISProposal
from jarvis.crsis.applier import ChangeApplier
from jarvis.crsis.api import ProposalAPI
import json

with open('$file') as f:
    data = json.load(f)

# Create proposal from data
proposal = CRSISProposal(
    proposal_id=data['proposal_id'],
    proposal_type=data['proposal_type'],
    target_file=data['target_file'],
    target_structure=data['target_structure'],
    proposed_change=data['proposed_change'],
    evidence=data.get('evidence', []),
    expected_impact=data['expected_impact'],
    rollback_path=data['rollback_path'],
)
proposal.status = 'approved'

applier = ChangeApplier('$ProjectRoot')
result = applier.apply(proposal)

if result.success:
    print("SUCCESS")
    print(f"Backup: {result.backup_path}")
else:
    print("FAILED")
    print(f"Error: {result.error}")
    print(f"Rolled back: {result.rolled_back}")
"@

    $output = python -c $pythonScript 2>&1

    if ($output -like "*SUCCESS*") {
        $proposal.status = "applied"
        $proposal.applied_at = (Get-Date -Format "o")
        $proposal | ConvertTo-Json -Depth 10 | Set-Content $file.FullName
        Write-Host "Proposal applied successfully!" -ForegroundColor Green
    } else {
        Write-Host "Application failed:" -ForegroundColor Red
        Write-Host $output
    }
}

function Show-Stats {
    $pending = (Get-PendingProposals).Count
    $all = Get-ChildItem "$ProposalsDir/*.json"

    $approved = 0
    $rejected = 0
    $applied = 0
    $rolledBack = 0

    foreach ($file in $all) {
        $content = Get-Content $file.FullName -Raw | ConvertFrom-Json
        switch ($content.status) {
            "approved" { $approved++ }
            "rejected" { $rejected++ }
            "applied" { $applied++ }
            "rolled_back" { $rolledBack++ }
        }
    }

    Write-Host "`nCRSIS Proposal Statistics" -ForegroundColor Cyan
    Write-Host "========================`n"
    Write-Host "Pending:     $pending" -ForegroundColor Yellow
    Write-Host "Approved:    $approved" -ForegroundColor Green
    Write-Host "Rejected:    $rejected" -ForegroundColor Red
    Write-Host "Applied:     $applied" -ForegroundColor Green
    Write-Host "Rolled back: $rolledBack" -ForegroundColor Magenta
    Write-Host ""
}

# Main command dispatch
switch ($Command.ToLower()) {
    "list" {
        $proposals = Get-PendingProposals
        if (-not $proposals) {
            Write-Host "No pending proposals." -ForegroundColor Gray
        } else {
            Write-Host "`nPending Proposals:" -ForegroundColor Cyan
            Write-Host "------------------"
            foreach ($p in $proposals) {
                Write-Host "`n[$($p.proposal_id)]" -ForegroundColor Yellow
                Write-Host "  Type: $($p.proposal_type)"
                Write-Host "  Target: $($p.target_file)"
                Write-Host "  Impact: $($p.expected_impact)"
                Write-Host "  Evidence: $($p.evidence.Count) findings, confidence: $($p.evidence[0].confidence)"
            }
        }
    }
    "show" {
        if (-not $ProposalId) {
            Write-Host "Usage: crsis_proposals.ps1 show <proposal_id>" -ForegroundColor Red
            exit 1
        }
        Show-Proposal $ProposalId
    }
    "approve" {
        if (-not $ProposalId) {
            Write-Host "Usage: crsis_proposals.ps1 approve <proposal_id>" -ForegroundColor Red
            exit 1
        }
        Approve-Proposal $ProposalId
    }
    "reject" {
        if (-not $ProposalId) {
            Write-Host "Usage: crsis_proposals.ps1 reject <proposal_id> [reason]" -ForegroundColor Red
            exit 1
        }
        Reject-Proposal $ProposalId $Reason
    }
    "apply" {
        if (-not $ProposalId) {
            Write-Host "Usage: crsis_proposals.ps1 apply <proposal_id>" -ForegroundColor Red
            exit 1
        }
        Apply-Proposal $ProposalId
    }
    "stats" {
        Show-Stats
    }
    default {
        Write-Host "CRSIS Proposals CLI" -ForegroundColor Cyan
        Write-Host "`nUsage: .\scripts\crsis_proposals.ps1 <command> [args]`n"
        Write-Host "Commands:"
        Write-Host "  list              - Show pending proposals"
        Write-Host "  show <id>         - Display proposal details"
        Write-Host "  approve <id>      - Approve proposal"
        Write-Host "  reject <id> <msg> - Reject with reason"
        Write-Host "  apply <id>        - Apply approved proposal"
        Write-Host "  stats             - Show statistics"
    }
}

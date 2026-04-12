"""ChangeApplier - Apply approved changes with validation and rollback."""

from __future__ import annotations


import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jarvis.crsis.code_modifier import CodeModifier
from jarvis.crsis.rollback import RollbackManager
from jarvis.crsis.validation import TestValidator
from jarvis.crsis.contracts import ChangeResult, CRSISProposal


@dataclass(frozen=True)
class ApplyResult:
    """Result of applying a proposal."""

    success: bool
    proposal_id: str
    backup_path: str | None = None
    validation_passed: bool = False
    validation_output: str = ""
    error: str | None = None
    rolled_back: bool = False


class ChangeApplier:
    """Apply approved CRSIS proposals with test validation and auto-rollback.

    Apply flow:
    1. Create temp copy of target file
    2. Apply code change to temp file via CodeModifier
    3. Run tiered validation tests on temp file
    4. Only on passing, create backup of live file and swap with temp
    5. On failure, delete temp and return failure
    """

    def __init__(
        self,
        project_root: str | None = None,
        code_modifier: CodeModifier | None = None,
        rollback_manager: RollbackManager | None = None,
        test_validator: TestValidator | None = None,
    ) -> None:
        self._project_root = Path(project_root) if project_root else Path.cwd()
        self._code_modifier = code_modifier or CodeModifier()
        self._rollback_manager = rollback_manager or RollbackManager(self._project_root)
        self._test_validator = test_validator or TestValidator(self._project_root)

    def apply(self, proposal: CRSISProposal) -> ApplyResult:
        """Apply an approved proposal.

        Args:
            proposal: CRSISProposal with status "approved"

        Returns:
            ApplyResult with success status and details
        """
        if proposal.status != "approved":
            return ApplyResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=f"Proposal not approved (status: {proposal.status})",
            )

        target_file = self._project_root / proposal.target_file
        if not target_file.exists():
            return ApplyResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=f"Target file not found: {proposal.target_file}",
            )

        # Step 1: Create temp copy of target file
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
            temp_path = Path(tf.name)
        
        try:
            shutil.copy2(target_file, temp_path)

            # Step 2: Apply code change to temp file
            # We need to tell _apply_change to use temp_path as target
            change_result = self._apply_change_to_path(temp_path, proposal)
            
            if not change_result.success:
                if temp_path.exists():
                    os.unlink(temp_path)
                return ApplyResult(
                    success=False,
                    proposal_id=proposal.proposal_id,
                    error=change_result.error or "Code change failed",
                )

            # Step 3: Run tiered validation on temp file
            validation_result = self._test_validator.validate(proposal, override_path=temp_path)

            if not validation_result.passed:
                if temp_path.exists():
                    os.unlink(temp_path)
                return ApplyResult(
                    success=False,
                    proposal_id=proposal.proposal_id,
                    validation_passed=False,
                    validation_output=validation_result.output,
                    error="Validation failed - live file untouched",
                )

            # Step 4: Success - create backup of live file and swap
            backup_path = self._rollback_manager.create_backup(target_file)
            os.replace(temp_path, target_file)

            return ApplyResult(
                success=True,
                proposal_id=proposal.proposal_id,
                backup_path=backup_path,
                validation_passed=True,
                validation_output=validation_result.output,
            )

        except Exception as e:
            if temp_path.exists():
                os.unlink(temp_path)
            return ApplyResult(
                success=False,
                proposal_id=proposal.proposal_id,
                error=str(e),
            )

    def _apply_change_to_path(self, target_path: Path, proposal: CRSISProposal) -> ChangeResult:
        """Apply the proposed change to a specific file path."""
        change_type = proposal.proposal_type
        target_str = str(target_path)

        if change_type == "new_phrase":
            change = proposal.proposed_change
            intent = change.get("intent")
            phrases = change.get("phrases", [])
            for phrase in phrases:
                res = self._code_modifier.add_dict_entry(target_str, proposal.target_structure, phrase, intent)
                if not res.success: return res
            return ChangeResult(success=True)
            
        elif change_type == "threshold_change":
            return self._code_modifier.update_threshold(target_str, proposal.target_structure, proposal.proposed_change.get("proposed"))
            
        elif change_type == "synonym_add":
            c = proposal.proposed_change
            return self._code_modifier.add_to_mapping(target_str, proposal.target_structure, c.get("category"), c.get("synonym"), c.get("intent"))
            
        elif change_type == "tool_registration":
            c = proposal.proposed_change
            return self._code_modifier.add_dict_entry(target_str, proposal.target_structure, c.get("tool_name"), c.get("handler_path"))
            
        elif change_type == "retention_change":
            return self._code_modifier.update_threshold(target_str, proposal.proposed_change.get("config_key"), proposal.proposed_change.get("proposed"))
            
        else:
            return ChangeResult(success=False, error=f"Unknown proposal type: {change_type}")

    def _apply_change(self, proposal: CRSISProposal) -> ChangeResult:
        """Legacy helper - redirects to live file."""
        return self._apply_change_to_path(self._project_root / proposal.target_file, proposal)


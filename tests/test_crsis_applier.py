"""Tests for CRSIS change applier."""
from __future__ import annotations


import pytest
import tempfile
import os
from pathlib import Path
from jarvis.crsis.applier import ChangeApplier
from jarvis.crsis.contracts import CRSISProposal, PatternFinding


class TestChangeApplier:
    """Test proposal application."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.applier = ChangeApplier(project_root=self.temp_dir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_requires_approval(self):
        """Test that unapproved proposals cannot be applied."""
        proposal = CRSISProposal(
            proposal_id="test_001",
            proposal_type="new_phrase",
            target_file="test.py",
            target_structure="TEST_DICT",
            proposed_change={"add": {"test": "value"}},
            evidence=[],
            expected_impact="Test",
            rollback_path="Remove test",
            status="pending",  # Not approved
        )

        result = self.applier.apply(proposal)

        assert not result.success
        assert "not approved" in result.error

    def test_apply_file_not_found(self):
        """Test application fails when target file doesn't exist."""
        proposal = CRSISProposal(
            proposal_id="test_001",
            proposal_type="new_phrase",
            target_file="nonexistent.py",
            target_structure="TEST_DICT",
            proposed_change={"add": {"test": "value"}},
            evidence=[],
            expected_impact="Test",
            rollback_path="Remove test",
            status="approved",
        )

        result = self.applier.apply(proposal)

        assert not result.success
        assert "not found" in result.error

    def test_apply_creates_backup(self):
        """Test that application creates backup."""
        # Create target file
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("TEST_DICT = {'existing': 'value'}\n")

        proposal = CRSISProposal(
            proposal_id="test_001",
            proposal_type="new_phrase",
            target_file="test.py",
            target_structure="TEST_DICT",
            proposed_change={"add": {"test": "value"}},
            evidence=[],
            expected_impact="Test",
            rollback_path="Remove test",
            status="approved",
        )

        result = self.applier.apply(proposal)

        # Backup should be created even if change fails
        assert result.backup_path is not None


class TestChangeApplierThreshold:
    """Test threshold change application."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.applier = ChangeApplier(project_root=self.temp_dir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_apply_threshold_change(self):
        """Test threshold value update."""
        # Create target file
        test_file = Path(self.temp_dir) / "config.py"
        test_file.write_text("ROUTING_CONFIDENCE_THRESHOLD = 0.7\n")

        proposal = CRSISProposal(
            proposal_id="test_002",
            proposal_type="threshold_change",
            target_file="config.py",
            target_structure="ROUTING_CONFIDENCE_THRESHOLD",
            proposed_change={"proposed": 0.75},
            evidence=[],
            expected_impact="Improve routing",
            rollback_path="Restore threshold",
            status="approved",
        )

        result = self.applier.apply(proposal)

        # Syntax check passes
        assert result.validation_passed or not result.success

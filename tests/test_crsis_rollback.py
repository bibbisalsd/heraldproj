"""Tests for CRSIS rollback manager."""
from __future__ import annotations


import pytest
import tempfile
from pathlib import Path
from jarvis.crsis.rollback import RollbackManager


class TestRollbackManager:
    """Test rollback operations."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = RollbackManager(project_root=Path(self.temp_dir))

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_backup(self):
        """Test backup creation."""
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("original content\n")

        backup_path = self.manager.create_backup(test_file)

        assert backup_path is not None
        assert Path(backup_path).exists()

    def test_restore_from_backup(self):
        """Test restoration from backup."""
        test_file = Path(self.temp_dir) / "test.py"
        original_content = "original content\n"
        test_file.write_text(original_content)

        backup_path = self.manager.create_backup(test_file)

        # Modify original
        test_file.write_text("modified content\n")

        # Restore
        success = self.manager.restore(backup_path)

        assert success
        assert test_file.read_text() == original_content

    def test_restore_latest(self):
        """Test restoring latest backup."""
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("version 1\n")

        # Create multiple backups
        self.manager.create_backup(test_file)
        test_file.write_text("version 2\n")
        self.manager.create_backup(test_file)

        # Modify again
        test_file.write_text("version 3\n")

        # Restore latest
        success = self.manager.restore_latest(test_file)

        assert success
        # Should restore to version 2 (latest backup)
        content = test_file.read_text()
        assert "version 2" in content

    def test_cleanup_old_backups(self):
        """Test cleanup of old backups."""
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("content\n")

        # Create backup
        self.manager.create_backup(test_file)

        # Cleanup (nothing should be removed - backups are fresh)
        removed = self.manager.cleanup(older_than_hours=1)

        assert removed == 0

    def test_verify_backup(self):
        """Test backup verification."""
        test_file = Path(self.temp_dir) / "test.py"
        test_file.write_text("content to verify\n")

        backup_path = self.manager.create_backup(test_file)

        # Verify should pass
        assert self.manager.verify_backup(backup_path) is True

        # Corrupt backup
        Path(backup_path).write_text("corrupted\n")

        # Verify should fail
        assert self.manager.verify_backup(backup_path) is False

    def test_backup_for_nonexistent_file(self):
        """Test backup creation for nonexistent file raises error."""
        test_file = Path(self.temp_dir) / "nonexistent.py"

        with pytest.raises(FileNotFoundError):
            self.manager.create_backup(test_file)

    def test_restore_nonexistent_backup(self):
        """Test restoration of nonexistent backup fails gracefully."""
        success = self.manager.restore("/nonexistent/backup.bak")
        assert success is False

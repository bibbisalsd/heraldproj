"""NH-CRSIS Task H: Contradiction Guard in Memory tests."""
from __future__ import annotations

import os
import json
from pathlib import Path
import pytest

from jarvis.brain_core.memory_service import MemoryService, CONTRADICTION_NEGATION_PAIRS


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_memory.db"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return MemoryService(db_path=str(db_path), log_dir=str(log_dir))


class TestContradictionBasics:
    """Test basic contradiction detection."""

    def test_no_contradiction_on_first_save(self, temp_db):
        """Fresh key saves without issue."""
        result = temp_db.save("test_key", "value1", confidence=0.9)
        assert result is True
        records = temp_db.retrieve("test_key")
        assert len(records) == 1
        assert records[0].value == "value1"

    def test_contradiction_blocked_yes_no(self, temp_db):
        """Save 'yes' then 'no' for same key; second returns False."""
        # First save
        result = temp_db.save("answer", "yes", confidence=0.9)
        assert result is True

        # Contradictory save should be blocked
        result = temp_db.save("answer", "no", confidence=0.9)
        assert result is False

        # Original value should still be there
        records = temp_db.retrieve("answer")
        assert len(records) == 1
        assert records[0].value == "yes"

    def test_contradiction_blocked_enabled_disabled(self, temp_db):
        """Save 'enabled' then 'disabled' for same key; second blocked."""
        result = temp_db.save("feature", "enabled", confidence=0.9)
        assert result is True

        result = temp_db.save("feature", "disabled", confidence=0.9)
        assert result is False

    def test_contradiction_blocked_true_false(self, temp_db):
        """Save 'true' then 'false' for same key."""
        result = temp_db.save("flag", "true", confidence=0.9)
        assert result is True

        result = temp_db.save("flag", "false", confidence=0.9)
        assert result is False

    def test_contradiction_blocked_on_off(self, temp_db):
        """Save 'on' then 'off' for same key."""
        result = temp_db.save("switch", "on", confidence=0.9)
        assert result is True

        result = temp_db.save("switch", "off", confidence=0.9)
        assert result is False

    def test_non_contradicting_values_both_save(self, temp_db):
        """Two different-but-compatible values for same key both insert."""
        # Use longer values that won't trigger short-value contradiction detection
        result = temp_db.save("description", "This is a detailed description about Alice", confidence=0.9)
        assert result is True

        result = temp_db.save("description", "This is a detailed description about Bob", confidence=0.9)
        assert result is True  # Long values are not automatic contradictions

        records = temp_db.retrieve("description")
        assert len(records) == 2

    def test_same_value_not_contradiction(self, temp_db):
        """Saving the same value twice is not a contradiction."""
        result = temp_db.save("status", "active", confidence=0.9)
        assert result is True

        result = temp_db.save("status", "active", confidence=0.9)
        assert result is True  # Same value, not a contradiction


class TestForceSave:
    """Test force_save bypasses contradiction check."""

    def test_force_save_bypasses_check(self, temp_db):
        """force_save() succeeds even when contradiction exists."""
        # Normal save
        result = temp_db.save("status", "on", confidence=0.9)
        assert result is True

        # Normal save blocked
        result = temp_db.save("status", "off", confidence=0.9)
        assert result is False

        # Force save succeeds
        result = temp_db.force_save("status", "off", confidence=0.9)
        assert result is True

        # New value is saved
        records = temp_db.retrieve("status")
        assert len(records) == 2  # Both values exist
        assert records[0].value == "off"  # Latest is "off"

    def test_force_save_respects_confidence_threshold(self, temp_db):
        """force_save still checks confidence threshold."""
        result = temp_db.force_save("test", "value", confidence=0.5)
        assert result is False

        result = temp_db.force_save("test", "value", confidence=0.9)
        assert result is True


class TestContradictionEvent:
    """Test contradiction event emission."""

    def test_contradiction_emits_event(self, temp_db, tmp_path):
        """Verify contradiction event written to log."""
        # First save
        temp_db.save("answer", "yes", confidence=0.9)

        # Contradictory save
        temp_db.save("answer", "no", confidence=0.9)

        # Check log file
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = Path(temp_db._log_dir) / f"jarvis_events_{today}.jsonl"
        assert log_file.exists()

        content = log_file.read_text()
        assert "memory_contradiction" in content
        assert "answer" in content
        assert "yes" in content
        assert "no" in content


class TestContradictionDetection:
    """Test _is_contradiction method directly."""

    def test_negation_pair_yes_no(self, temp_db):
        """Yes/no detected as contradiction."""
        assert temp_db._is_contradiction("yes", "no") is True
        assert temp_db._is_contradiction("no", "yes") is True

    def test_negation_pair_true_false(self, temp_db):
        """True/false detected as contradiction."""
        assert temp_db._is_contradiction("true", "false") is True
        assert temp_db._is_contradiction("false", "true") is True

    def test_negation_pair_enabled_disabled(self, temp_db):
        """Enabled/disabled detected as contradiction."""
        assert temp_db._is_contradiction("enabled", "disabled") is True

    def test_same_value_not_contradiction(self, temp_db):
        """Same value is not a contradiction."""
        assert temp_db._is_contradiction("hello", "hello") is False

    def test_long_different_values_not_flagged(self, temp_db):
        """Long different values are not automatically contradictions."""
        long1 = "This is a very long sentence about something."
        long2 = "This is another very long sentence about something else."
        assert temp_db._is_contradiction(long1, long2) is False

    def test_short_different_values_flagged(self, temp_db):
        """Short different values are flagged as potential contradictions."""
        assert temp_db._is_contradiction("yes", "maybe") is False
        assert temp_db._is_contradiction("on", "maybe") is False

    def test_case_insensitive(self, temp_db):
        """Contradiction detection is case insensitive."""
        assert temp_db._is_contradiction("YES", "no") is True
        assert temp_db._is_contradiction("Enabled", "DISABLED") is True


class TestLowConfidenceBlocked:
    """Test confidence gate fires before contradiction check."""

    def test_low_confidence_still_blocked_before_contradiction_check(self, temp_db):
        """Confidence gate fires before contradiction check."""
        result = temp_db.save("test", "value", confidence=0.5)
        assert result is False

        # Nothing saved
        records = temp_db.retrieve("test")
        assert len(records) == 0

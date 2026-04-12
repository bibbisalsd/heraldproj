"""NH-CRSIS Task I: Confidence Decay tests."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis.brain_core.memory_service import MemoryService, DECAY_HALF_LIFE_DAYS


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_memory.db"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return MemoryService(db_path=str(db_path), log_dir=str(log_dir))


class TestDecayedConfidence:
    """Test _decayed_confidence method."""

    def test_fresh_fact_has_full_confidence(self, temp_db):
        """Just-saved fact has full confidence."""
        now = datetime.now(timezone.utc).isoformat()
        decayed = temp_db._decayed_confidence(0.9, now)
        assert decayed == 0.9  # No decay for fresh fact

    def test_decay_half_life_at_30_days(self, temp_db):
        """Fact at exactly 30 days old has ~50% of original confidence."""
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        decayed = temp_db._decayed_confidence(1.0, thirty_days_ago)
        assert 0.48 <= decayed <= 0.52  # Approximately 50%

    def test_decay_at_60_days(self, temp_db):
        """Fact at 60 days old has ~25% of original confidence."""
        sixty_days_ago = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        decayed = temp_db._decayed_confidence(1.0, sixty_days_ago)
        assert 0.23 <= decayed <= 0.27  # Approximately 25% (0.5^2)

    def test_decay_at_90_days(self, temp_db):
        """Fact at 90 days old has ~12.5% of original confidence."""
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        decayed = temp_db._decayed_confidence(1.0, ninety_days_ago)
        assert 0.11 <= decayed <= 0.14  # Approximately 12.5% (0.5^3)

    def test_high_confidence_survives_longer(self, temp_db):
        """High confidence fact survives longer than low confidence fact."""
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        # High confidence fact (1.0) decays to ~0.5, still above 0.75 threshold? No, below
        high_decayed = temp_db._decayed_confidence(1.0, thirty_days_ago)
        assert high_decayed < 0.75  # Even high confidence decays below threshold at 30 days

        # But at 15 days, high confidence should still be above threshold
        fifteen_days_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        high_decayed_15 = temp_db._decayed_confidence(1.0, fifteen_days_ago)
        assert high_decayed_15 > 0.70  # Should be around 0.71

    def test_malformed_created_at_does_not_crash(self, temp_db):
        """Graceful fallback on bad timestamp."""
        decayed = temp_db._decayed_confidence(0.9, "invalid-timestamp")
        assert decayed == 0.9  # Returns original confidence as fallback

    def test_malformed_created_at_empty_string(self, temp_db):
        """Empty timestamp returns original confidence."""
        decayed = temp_db._decayed_confidence(0.9, "")
        assert decayed == 0.9

    def test_none_confidence_handled(self, temp_db):
        """None confidence is handled gracefully."""
        # This tests the TypeError path
        try:
            decayed = temp_db._decayed_confidence(None, "2024-01-01T00:00:00+00:00")  # type: ignore
            # If no exception, it should return None (the input) as fallback
            assert decayed is None  # type: ignore
        except TypeError:
            pass  # Also acceptable


class TestRetrieveWithDecay:
    """Test retrieve() filters by decayed confidence."""

    def test_fresh_fact_passes_threshold(self, temp_db):
        """Just-saved fact with confidence 0.9 is retrievable."""
        temp_db.save("fresh_key", "fresh_value", confidence=0.9)
        records = temp_db.retrieve("fresh_key")
        assert len(records) == 1
        assert records[0].value == "fresh_value"

    def test_ancient_fact_filtered_out(self, temp_db):
        """Fact with created_at 120 days ago + confidence 0.8 falls below threshold."""
        # Manually insert an old record - use explicit old date (200 days ago from April 2026)
        ancient_date = "2025-09-01T00:00:00+00:00"  # Fixed old date, ~215 days before April 2026
        with temp_db._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_facts (key, value, confidence, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("ancient_key", "ancient_value", 0.8, ancient_date),
            )

        records = temp_db.retrieve("ancient_key")
        # 0.8 * 0.5^(215/30) = 0.8 * 0.0069 = 0.0055, well below 0.75 threshold
        assert len(records) == 0

    def test_old_fact_with_high_confidence_still_filtered(self, temp_db):
        """Even high confidence facts decay below threshold eventually."""
        # Use explicit old date (90 days ago from April 2026 = early January 2026)
        old_date = "2026-01-01T00:00:00+00:00"  # ~95 days before April 2026
        with temp_db._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_facts (key, value, confidence, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("old_key", "old_value", 0.95, old_date),
            )

        records = temp_db.retrieve("old_key")
        # 0.95 * 0.5^(95/30) = 0.95 * 0.11 = 0.10, below 0.75 threshold
        assert len(records) == 0

    def test_recent_fact_with_moderate_confidence_retrieved(self, temp_db):
        """Recent fact with moderate confidence is retrievable."""
        # Use explicit recent date (1 day ago from April 2026)
        # 0.9 * 0.5^(1/30) = 0.9 * 0.977 = 0.88, above 0.75 threshold
        recent_date = "2026-04-05T00:00:00+00:00"  # 1 day before April 6, 2026
        with temp_db._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_facts (key, value, confidence, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("recent_key", "recent_value", 0.9, recent_date),
            )

        records = temp_db.retrieve("recent_key")
        assert len(records) == 1


class TestRetrieveWithDecayScores:
    """Test retrieve_with_decay_scores() returns tuples."""

    def test_retrieve_with_decay_scores_returns_tuples(self, temp_db):
        """Returns (MemoryRecord, float) tuples."""
        temp_db.save("scored_key", "scored_value", confidence=0.9)
        results = temp_db.retrieve_with_decay_scores("scored_key")

        assert len(results) == 1
        record, score = results[0]
        assert isinstance(record, type(temp_db.retrieve("scored_key")[0]))
        assert isinstance(score, float)
        assert 0.85 <= score <= 0.95  # Should be close to original 0.9

    def test_retrieve_with_decay_scores_empty(self, temp_db):
        """Returns empty list for non-existent key."""
        results = temp_db.retrieve_with_decay_scores("nonexistent")
        assert len(results) == 0


class TestForceSaveAlsoDecays:
    """Test that force_save() facts also decay."""

    def test_force_save_fact_also_decays(self, temp_db):
        """force_save() facts decay the same way as normal saves."""
        # Save with force_save
        temp_db.force_save("force_key", "force_value", confidence=0.9)

        # Verify it's retrievable when fresh
        records = temp_db.retrieve("force_key")
        assert len(records) == 1

        # Manually age the record - use explicit old date
        ancient_date = "2025-09-01T00:00:00+00:00"  # ~215 days before April 2026
        with temp_db._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET created_at = ? WHERE key = ?",
                (ancient_date, "force_key"),
            )

        # Now it should be filtered out
        records = temp_db.retrieve("force_key")
        assert len(records) == 0

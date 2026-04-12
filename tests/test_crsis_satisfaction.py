"""Tests for CRSIS satisfaction detection."""
from __future__ import annotations


import pytest
from jarvis.crsis.satisfaction_detector import SatisfactionDetector
from jarvis.crsis.contracts import SatisfactionSignal


class TestSatisfactionDetector:
    """Test satisfaction signal detection."""

    def setup_method(self):
        self.detector = SatisfactionDetector()

    def test_detect_correction(self):
        """Test detection of correction signals."""
        result = self.detector.detect(
            user_message="No, that's not what I meant",
            conversation_history=[],
            follow_up_window_active=True,
        )

        assert result.signal is not None
        assert result.signal.signal_type == "correction"
        assert "no," in result.raw_indicators["correction_matches"]

    def test_detect_acceptance(self):
        """Test detection of acceptance signals."""
        result = self.detector.detect(
            user_message="Thanks, that works",
            conversation_history=[],
        )

        assert result.signal is not None
        assert result.signal.signal_type == "acceptance"

    def test_detect_re_ask(self):
        """Test detection of re-ask signals."""
        history = [
            {"role": "user", "content": "How do I create a file?"},
            {"role": "assistant", "content": "Use the file_write tool."},
            {"role": "user", "content": "How do I create a file?"},
        ]

        result = self.detector.detect(
            user_message="How do I create a file?",
            conversation_history=history,
        )

        assert result.signal is not None
        assert result.signal.signal_type == "re_ask"
        assert result.raw_indicators["re_ask_detected"] is True

    def test_detect_abandonment(self):
        """Test detection of abandonment signals."""
        result = self.detector.detect(
            user_message="Never mind, it's fine",
            conversation_history=[],
        )

        assert result.signal is not None
        assert result.signal.signal_type == "abandonment"

    def test_no_signal_for_neutral_message(self):
        """Test that neutral messages don't trigger signals."""
        result = self.detector.detect(
            user_message="What's the weather today?",
            conversation_history=[],
        )

        assert result.signal is None

    def test_add_correction_pattern(self):
        """Test adding custom correction patterns."""
        self.detector.add_correction_pattern("that's wrong")
        result = self.detector.detect(
            user_message="That's wrong, try again",
            conversation_history=[],
        )

        assert result.signal is not None
        assert result.signal.signal_type == "correction"
        assert "that's wrong" in result.raw_indicators["correction_matches"]

    def test_similarity_calculation(self):
        """Test string similarity calculation."""
        s1 = "create a new file"
        s2 = "create a new file"
        s3 = "delete the file"

        assert self.detector._similarity(s1, s2) == 1.0
        assert self.detector._similarity(s1, s3) > 0.0
        assert self.detector._similarity(s1, "completely different") < 0.5

"""Tests for CRSIS decision log analyzer."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone, timedelta
from jarvis.crsis.analyzer import DecisionLogAnalyzer
from jarvis.crsis.contracts import PatternFinding


class MockEventLog:
    """Mock event log for testing."""

    def __init__(self, events):
        self._events = events

    def read_log(self, after=None):
        if after is None:
            return self._events
        return [e for e in self._events if e.get("timestamp", "") > after]


class TestDecisionLogAnalyzer:
    """Test decision log analysis."""

    def setup_method(self):
        self.now = datetime.now(timezone.utc)
        self.events = []

    def _make_event(self, event_type, payload, offset_minutes=0):
        ts = self.now - timedelta(minutes=offset_minutes)
        return {
            "event_type": event_type,
            "payload": payload,
            "timestamp": ts.isoformat(),
        }

    def test_detect_misrouting(self):
        """Test detection of misrouted intents."""
        # Create dispatch events
        for i in range(5):
            self.events.append(self._make_event(
                "intent_dispatch",
                {"intent": "file_operation"},
                offset_minutes=i * 2,
            ))

        # Create correction signals
        for i in range(3):
            self.events.append(self._make_event(
                "satisfaction_signal",
                {"signal_type": "correction", "intent": "file_operation"},
                offset_minutes=i * 3 + 1,
            ))

        log = MockEventLog(self.events)
        analyzer = DecisionLogAnalyzer(log)
        findings = analyzer.analyze_last_n_hours(1)

        misrouting_findings = [f for f in findings if f.pattern_type == "misrouting"]
        assert len(misrouting_findings) >= 1
        assert "file_operation" in misrouting_findings[0].affected_component

    def test_detect_empty_tool_results(self):
        """Test detection of tools returning empty results."""
        # Create tool call events with empty results
        for i in range(6):
            self.events.append(self._make_event(
                "tool_call",
                {"tool_name": "web_search", "result": None},
                offset_minutes=i * 2,
            ))

        log = MockEventLog(self.events)
        analyzer = DecisionLogAnalyzer(log)
        findings = analyzer.analyze_last_n_hours(1)

        empty_tool_findings = [f for f in findings if f.pattern_type == "empty_tool"]
        assert len(empty_tool_findings) >= 1
        assert "web_search" in empty_tool_findings[0].affected_component

    def test_detect_correction_cluster(self):
        """Test detection of correction clusters."""
        # Create multiple corrections within 5 minutes
        for i in range(4):
            self.events.append(self._make_event(
                "satisfaction_signal",
                {"signal_type": "correction", "intent": "file_edit"},
                offset_minutes=i,  # 1 minute apart
            ))

        log = MockEventLog(self.events)
        analyzer = DecisionLogAnalyzer(log)
        findings = analyzer.analyze_last_n_hours(1)

        cluster_findings = [f for f in findings if f.pattern_type == "correction_cluster"]
        assert len(cluster_findings) >= 1

    def test_no_findings_with_insufficient_data(self):
        """Test that insufficient data produces no findings."""
        # Only 1 correction - below threshold
        self.events.append(self._make_event(
            "satisfaction_signal",
            {"signal_type": "correction", "intent": "test"},
            offset_minutes=1,
        ))

        log = MockEventLog(self.events)
        analyzer = DecisionLogAnalyzer(log)
        findings = analyzer.analyze_last_n_hours(1)

        assert len(findings) == 0

    def test_analyze_with_empty_log(self):
        """Test analysis with empty event log."""
        log = MockEventLog([])
        analyzer = DecisionLogAnalyzer(log)
        findings = analyzer.analyze_last_n_hours(1)

        assert len(findings) == 0

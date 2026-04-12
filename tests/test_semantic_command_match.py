from __future__ import annotations
from jarvis.brain_core.semantic_command_match import SemanticCommandMatcher


def test_semantic_command_match_finds_status_intent():
    matcher = SemanticCommandMatcher()
    result = matcher.match("what are you doing right now")
    assert result.intent == "job_status"
    assert result.score >= 0.5


def test_semantic_command_match_returns_none_for_unrelated_text():
    matcher = SemanticCommandMatcher()
    result = matcher.match("completely unrelated phrase")
    assert result.intent is None

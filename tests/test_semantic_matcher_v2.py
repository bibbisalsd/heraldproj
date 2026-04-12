from __future__ import annotations

from jarvis.brain_core.semantic_command_match import SemanticCommandMatcher, _bigrams, _expand_synonyms


def test_exact_phrase_still_matches() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("what time is it")
    assert result.intent == "time_query"
    assert result.score >= 0.5


def test_synonym_expansion_time() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("show me the time")
    assert result.intent == "time_query"


def test_synonym_expansion_status() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("whats happening")
    assert result.intent == "job_status"


def test_synonym_cancel() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("abort the task")
    assert result.intent == "job_cancel"


def test_synonym_free() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("let me know when finished")
    assert result.intent == "notify_when_free"


def test_bigram_boost() -> None:
    matcher = SemanticCommandMatcher()
    direct = matcher.match("what time is it now")
    reversed_order = matcher.match("time what is it now")

    assert direct.intent == "time_query"
    assert reversed_order.intent == "time_query"
    assert direct.score >= reversed_order.score


def test_no_match_garbage() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("purple elephant sandwich")
    assert result.intent is None


def test_threshold_respected() -> None:
    matcher = SemanticCommandMatcher()
    result = matcher.match("what please")
    assert result.intent is None
    assert result.score < 0.5


def test_expand_synonyms_function() -> None:
    expanded = _expand_synonyms({"show", "clock", "available"})
    assert "show" in expanded
    assert "clock" in expanded
    assert "available" in expanded
    assert "what" in expanded
    assert "time" in expanded
    assert "free" in expanded


def test_bigrams_function() -> None:
    assert _bigrams(["what", "time", "is"]) == {"what_time", "time_is"}
    assert _bigrams(["single"]) == set()

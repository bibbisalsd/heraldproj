from __future__ import annotations
from jarvis.brain_core.deterministic_understanding import analyze_utterance


def test_analyzer_detects_self_workflow_question_without_exact_phrase():
    signals = analyze_utterance("Jarvis, could you explain how you're built?")

    assert signals.asks_workflow is True
    assert signals.asks_identity is False


def test_analyzer_detects_code_location_question_from_features():
    signals = analyze_utterance("Where do you keep your source files?")

    assert signals.asks_code_location is True
    assert signals.mentions_codebase is True


def test_analyzer_distinguishes_wellbeing_from_status():
    wellbeing = analyze_utterance("Hello Jarvis, are you okay?")
    status = analyze_utterance("Jarvis, are you busy with a task?")

    assert wellbeing.asks_wellbeing is True
    assert wellbeing.asks_status is False
    assert status.asks_status is True


def test_analyzer_extracts_owner_memory_updates_and_recalls():
    update = analyze_utterance("My name is James")
    intro = analyze_utterance("I am James, your creator")
    age = analyze_utterance("I am 32 years old")
    summary = analyze_utterance("What do you know about me?")

    assert update.declared_name == "James"
    assert intro.declared_name == "James"
    assert update.asks_name_recall is False
    assert age.declared_age == "32"
    assert summary.asks_owner_summary is True


def test_analyzer_distinguishes_day_and_date_queries():
    day = analyze_utterance("Jarvis, what day is it?")
    date = analyze_utterance("Jarvis, what date is it?")

    assert day.asks_day is True
    assert day.asks_time is False
    assert date.asks_date is True
    assert date.asks_time is False


def test_analyzer_detects_hearing_check():
    hearing = analyze_utterance("Javis, can you hear me?")

    assert hearing.asks_hearing_check is True
    assert hearing.asks_status is False

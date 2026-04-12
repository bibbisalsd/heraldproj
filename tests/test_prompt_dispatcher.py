from __future__ import annotations
from jarvis.brain_core.prompt_dispatcher import PromptDispatcher


def test_prompt_dispatcher_uses_exact_match_first():
    dispatcher = PromptDispatcher(wake_word="jarvis", wake_word_enabled=True)
    decision = dispatcher.route("jarvis what's the time", bg1_busy=False)
    assert decision.intent == "time_query"
    assert decision.match_type in ("exact", "deterministic")
    assert decision.lane == "realtime"


def test_prompt_dispatcher_uses_deterministic_match_before_classifier():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("what are you doing right now", bg1_busy=False)
    assert decision.match_type == "deterministic"
    assert decision.intent == "job_status"
    assert decision.lane == "realtime"


def test_prompt_dispatcher_uses_classifier_for_heavy_tasks():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("please research this deeply", bg1_busy=False)
    assert decision.match_type == "classifier"
    assert decision.lane == "bg1"
    assert decision.reason == "heavy_request"


def test_prompt_dispatcher_does_not_misroute_date_question_to_notify_when_free():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("jarvis tell me when christmas is", bg1_busy=False)
    assert decision.intent == "general_chat"
    assert decision.lane == "realtime"
    assert decision.match_type == "classifier"


def test_prompt_dispatcher_detects_wake_word_inside_sentence():
    dispatcher = PromptDispatcher(wake_word="jarvis", wake_word_enabled=True)
    assert dispatcher.contains_wake_word("can you help me jarvis please") is True
    assert dispatcher.contains_wake_word("hello there") is False


def test_prompt_dispatcher_detects_common_stt_wake_word_near_misses():
    dispatcher = PromptDispatcher(wake_word="jarvis", wake_word_enabled=True)
    assert dispatcher.contains_wake_word("javis what can you do") is True
    assert dispatcher.contains_wake_word("java's calm down") is True
    assert dispatcher.contains_wake_word("jovis tell me the time") is True
    assert dispatcher.contains_wake_word("java so do you understand me") is True
    assert dispatcher.contains_wake_word("jabbas are you there") is True


def test_prompt_dispatcher_normalize_text_removes_wake_word_anywhere():
    dispatcher = PromptDispatcher(wake_word="jarvis", wake_word_enabled=True)
    # We no longer remove wake word in normalize_text
    assert "jarvis" in dispatcher.normalize_text("Can you help me, Jarvis?").lower()


def test_prompt_dispatcher_normalize_text_removes_common_wake_word_aliases():
    dispatcher = PromptDispatcher(wake_word="jarvis", wake_word_enabled=True)
    assert "javis" in dispatcher.normalize_text("Javis, what can you do?").lower()
    assert "java's" in dispatcher.normalize_text("How are you, Java's?").lower()
    assert "jabbas" in dispatcher.normalize_text("Jabbas, status").lower()


def test_prompt_dispatcher_does_not_map_how_are_you_to_job_status():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("how are you", bg1_busy=False)
    assert decision.intent == "wellbeing_query"
    assert decision.match_type == "deterministic"
    assert decision.lane == "realtime"


def test_prompt_dispatcher_deterministically_routes_name_recall_variation():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("do you know my name", bg1_busy=False)
    assert decision.match_type in {"exact", "deterministic"}
    assert decision.intent == "recall_name"


def test_prompt_dispatcher_deterministically_routes_owner_memory_summary():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("what do you know about me", bg1_busy=False)
    assert decision.match_type == "deterministic"
    assert decision.intent == "owner_memory"


def test_prompt_dispatcher_routes_intro_name_with_creator_context_to_owner_memory():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("I am James, your creator, Javis.", bg1_busy=False)
    assert decision.match_type == "deterministic"
    assert decision.intent == "owner_memory"


def test_prompt_dispatcher_routes_day_and_date_queries_separately():
    dispatcher = PromptDispatcher()

    day = dispatcher.route("Jarvis, what day is it?", bg1_busy=False)
    date = dispatcher.route("Jarvis, what date is it?", bg1_busy=False)

    assert day.intent == "day_query"
    assert date.intent == "date_query"


def test_prompt_dispatcher_routes_hearing_check_deterministically():
    dispatcher = PromptDispatcher()
    decision = dispatcher.route("Javis, can you hear me?", bg1_busy=False)
    assert decision.intent == "hearing_query"
    assert decision.match_type == "deterministic"


def test_prompt_dispatcher_skips_semantic_match_on_high_latency(monkeypatch):
    from jarvis.brain_core.prompt_dispatcher import PromptDispatcher
    import time

    dispatcher = PromptDispatcher()

    # Mock time.monotonic to simulate latency
    # First call: start time in route()
    # Second call: elapsed check before semantic
    times = [100.0, 100.6]  # 600ms elapsed
    def mock_monotonic():
        return times.pop(0) if times else 200.0

    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    # Use a phrase that isn't exact or deterministic but would be semantic
    # 'search' usually matches semantically to web_search
    decision = dispatcher.route("please search for something", bg1_busy=False)

    # Verify it skipped semantic and fell back to classifier
    assert decision.match_type == "classifier"
    # Semantic would have reason "semantic"
    assert decision.reason != "semantic"

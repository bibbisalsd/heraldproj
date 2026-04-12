from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from jarvis.brain_core.conversation_buffer import ConversationBuffer, TurnSummary


def _make_summary(text: str = "hello", intent: str = "greeting") -> TurnSummary:
    return TurnSummary(
        user_text=text,
        intent=intent,
        response_summary=f"Response to: {text}",
        timestamp="2026-03-31T12:00:00+00:00",
    )


def test_append_and_recent() -> None:
    buffer = ConversationBuffer()
    buffer.append(_make_summary("one"))
    buffer.append(_make_summary("two"))
    buffer.append(_make_summary("three"))

    recent = buffer.recent()
    assert [item.user_text for item in recent] == ["one", "two", "three"]


def test_overflow_evicts_oldest() -> None:
    buffer = ConversationBuffer(max_turns=3)
    for idx in range(5):
        buffer.append(_make_summary(f"text-{idx}"))

    recent = buffer.recent()
    assert [item.user_text for item in recent] == ["text-2", "text-3", "text-4"]


def test_recent_with_custom_n() -> None:
    buffer = ConversationBuffer()
    for idx in range(5):
        buffer.append(_make_summary(f"text-{idx}"))

    recent = buffer.recent(2)
    assert [item.user_text for item in recent] == ["text-3", "text-4"]


def test_recent_when_n_exceeds_size() -> None:
    buffer = ConversationBuffer()
    buffer.append(_make_summary("one"))
    buffer.append(_make_summary("two"))

    recent = buffer.recent(10)
    assert [item.user_text for item in recent] == ["one", "two"]


def test_clear() -> None:
    buffer = ConversationBuffer()
    buffer.append(_make_summary("one"))
    buffer.append(_make_summary("two"))

    buffer.clear()

    assert buffer.size == 0
    assert buffer.recent() == []


def test_turn_summary_is_frozen() -> None:
    summary = _make_summary()
    with pytest.raises(FrozenInstanceError):
        summary.user_text = "updated"


def test_empty_buffer_recent() -> None:
    buffer = ConversationBuffer()
    assert buffer.recent() == []

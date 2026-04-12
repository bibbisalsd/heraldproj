from __future__ import annotations
import pytest

from jarvis.brain_core.turn_state_machine import TurnStateMachine


def test_turn_state_machine_happy_path():
    sm = TurnStateMachine()
    sm.transition("INGRESS_RECEIVED")
    sm.transition("ROUTED")
    sm.transition("RUNNING")
    sm.transition("RENDERED")
    sm.transition("DELIVERED")
    assert sm.state == "DELIVERED"


def test_turn_state_machine_rejects_invalid_transition():
    sm = TurnStateMachine()
    with pytest.raises(ValueError):
        sm.transition("RUNNING")

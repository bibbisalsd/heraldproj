from __future__ import annotations

from dataclasses import dataclass


TURN_STATES = (
    "IDLE",
    "INGRESS_RECEIVED",
    "ROUTED",
    "RUNNING",
    "RENDERED",
    "DELIVERED",
    "FAILED",
)


ALLOWED_TURN_TRANSITIONS = {
    "IDLE": {"INGRESS_RECEIVED"},
    "INGRESS_RECEIVED": {"ROUTED", "FAILED"},
    "ROUTED": {"RUNNING", "FAILED"},
    "RUNNING": {"RENDERED", "FAILED"},
    "RENDERED": {"DELIVERED", "FAILED"},
    "DELIVERED": {"IDLE"},
    "FAILED": {"IDLE"},
}


@dataclass
class TurnStateMachine:
    state: str = "IDLE"
    reason_code: str = ""

    def transition(self, next_state: str, reason_code: str = "") -> str:
        if next_state not in TURN_STATES:
            raise ValueError(f"unknown_state:{next_state}")
        allowed = ALLOWED_TURN_TRANSITIONS[self.state]
        if next_state not in allowed:
            raise ValueError(f"invalid_transition:{self.state}->{next_state}")
        self.state = next_state
        self.reason_code = reason_code
        return self.state

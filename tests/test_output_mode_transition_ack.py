from __future__ import annotations
from jarvis.brain_core.output_mode import OutputModeController


def test_output_mode_transition_ack_success():
    ctl = OutputModeController()
    ack = ctl.set_mode("active_addon_text")
    assert ack.ok is True
    assert ack.mode == "active_addon_text"


def test_output_mode_transition_ack_rejects_invalid_mode():
    ctl = OutputModeController()
    ack = ctl.set_mode("invalid_mode")
    assert ack.ok is False
    assert ack.mode == "local_voice"

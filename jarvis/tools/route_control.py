from __future__ import annotations

from jarvis.brain_core.output_mode import OutputModeController


def set_output_mode(controller: OutputModeController, mode: str) -> dict:
    ack = controller.set_mode(mode)
    return {"ok": ack.ok, "mode": ack.mode, "message": ack.message}

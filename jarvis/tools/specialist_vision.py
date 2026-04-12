from __future__ import annotations

from jarvis.specialists.specialist_vision import run


def execute(task: str) -> dict:
    return run(task)

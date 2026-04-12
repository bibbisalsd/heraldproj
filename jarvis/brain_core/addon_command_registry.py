from __future__ import annotations

from typing import Callable, Optional


CommandHandler = Callable[[], str]


class AddonCommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandHandler] = {}

    def register(self, addon_id: str, command: str, handler: CommandHandler) -> None:
        namespaced = f"{addon_id}:{command}".lower()
        self._commands[namespaced] = handler

    def execute(self, addon_id: str, command: str) -> Optional[str]:
        namespaced = f"{addon_id}:{command}".lower()
        handler = self._commands.get(namespaced)
        if handler is None:
            return None
        return handler()

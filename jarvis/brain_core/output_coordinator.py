from __future__ import annotations

from dataclasses import dataclass


from .contracts import RenderedReply


@dataclass
class DeliveryResult:
    sink: str
    delivered: bool
    detail: str


class OutputCoordinator:
    def __init__(self) -> None:
        self._fallback_order = [
            "local_voice",
            "discord_voice",
            "discord_text",
            "active_addon_text",
            "local_text_log",
        ]

    def fallback_order(self) -> list[str]:
        return list(self._fallback_order)

    def deliver(
        self, reply: RenderedReply, sink_status: dict[str, bool]
    ) -> DeliveryResult:
        primary = (
            reply.sink
            if reply.sink in self._fallback_order
            else self._fallback_order[0]
        )
        ordered = self._ordered_candidates(primary)
        for sink in ordered:
            if sink_status.get(sink, False):
                return DeliveryResult(sink=sink, delivered=True, detail="ok")
        return DeliveryResult(sink="none", delivered=False, detail="no_healthy_sink")

    def _ordered_candidates(self, primary: str) -> list[str]:
        text_order = ["discord_text", "active_addon_text", "local_text_log"]

        if primary == "discord_voice":
            ordered = ["discord_voice", *text_order, "local_voice"]
        elif primary in text_order:
            ordered = [
                primary,
                *[sink for sink in text_order if sink != primary],
                "local_voice",
                "discord_voice",
            ]
        elif primary == "local_voice":
            ordered = [
                "local_voice",
                "active_addon_text",
                "local_text_log",
                "discord_text",
                "discord_voice",
            ]
        else:
            ordered = [primary] + [
                sink for sink in self._fallback_order if sink != primary
            ]

        return ordered

from __future__ import annotations

from jarvis.brain_core.contracts import AddonManifest


def build_manifest() -> AddonManifest:
    return AddonManifest(
        addon_id="discord",
        addon_name="Discord Addon",
        version="0.2.0",
        enabled_by_default=False,
        safe_in_degraded_mode=True,
        tools=("discord.join_voice", "discord.leave_voice"),
        input_bridges=("discord_text_bridge",),
        output_sinks=("discord_text_sink",),
        audio_channels=("discord_voice",),
        required_permissions=("addon_control",),
        startup_hook="startup",
        shutdown_hook="shutdown",
        healthcheck_hook="healthcheck",
        command_pack=("discord output on", "discord output off", "discord listen on", "discord listen off", "discord join voice", "discord leave voice"),
        permission_mapper="map_identity_to_profile",
        capability_summary="Discord text/voice bridge with channel controls, loop prevention, and health monitoring",
    )

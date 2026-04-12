from __future__ import annotations
from jarvis.brain_core.addon_audio_pipeline import AddonAudioChannel, AddonAudioPipeline
from jarvis.brain_core.ingress_hub import IngressHub


def test_addon_audio_pipeline_emits_into_ingress_hub():
    ingress_hub = IngressHub()
    pipeline = AddonAudioPipeline(emit_raw_event=ingress_hub.accept_raw_event)
    pipeline.register_channel(AddonAudioChannel(channel_id="discord_voice", addon_id="discord"))

    result = pipeline.emit(channel_id="discord_voice", speaker_id="user_1", payload="hello jarvis")
    assert result["ok"] == "true"
    assert len(ingress_hub.events) == 1
    assert ingress_hub.events[0].addon_id == "discord"


def test_addon_audio_pipeline_blocked_when_disabled():
    ingress_hub = IngressHub()
    pipeline = AddonAudioPipeline(emit_raw_event=ingress_hub.accept_raw_event)
    pipeline.register_channel(AddonAudioChannel(channel_id="discord_voice", addon_id="discord"))
    pipeline.set_channel_enabled("discord_voice", False)

    result = pipeline.emit(channel_id="discord_voice", speaker_id="user_1", payload="hello jarvis")
    assert result["ok"] == "false"
    assert result["reason"] == "channel_disabled"

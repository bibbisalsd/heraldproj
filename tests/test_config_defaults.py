from __future__ import annotations
from jarvis.config import JARVIS_VERSION, build_default_config, capability_map


def test_config_defaults_are_locked():
    cfg = build_default_config()
    assert JARVIS_VERSION.startswith("0.")
    assert cfg.bg1_max_active_jobs == 1
    assert cfg.bg1_max_queue_length == 1
    assert cfg.bg1_queue_ttl_seconds == 120
    assert cfg.core_output_default == "local_voice"
    assert cfg.renderer_model_preferred == "gemma4:e2b"
    assert cfg.renderer_model_fallback == "gemma4:e4b"
    assert cfg.vision_lite_model == "gemma4:e2b"
    assert cfg.vision_bg1_model == "qwen3-vl:8b"
    assert cfg.code_bg1_model == "deepcoder:14b"
    assert cfg.embedding_model == "nomic-embed-text-v2-moe"
    assert cfg.tts_model == "Kokoro-82M"
    assert cfg.renderer_max_packet_tokens == 384


def test_permission_profiles_are_authoritative():
    caps = capability_map()
    assert set(caps.keys()) == {"owner", "trusted", "guest"}
    assert caps["owner"]["file_write"] is True
    assert caps["trusted"]["file_write"] is False
    assert caps["guest"]["heavy_tasks"] is False

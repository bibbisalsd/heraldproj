from __future__ import annotations

from dataclasses import dataclass


JARVIS_VERSION = "0.1.0-alpha.1"


@dataclass(frozen=True)
class JarvisConfig:
    bg1_max_active_jobs: int = 1
    bg1_max_queue_length: int = 1
    bg1_queue_ttl_seconds: int = 120
    core_output_default: str = "local_voice"
    transcript_retention_days: int = 14
    artifact_retention_days: int = 7
    memory_retention_days: int = 90
    retention_purge_interval_hours: int = 24
    wake_word_enabled: bool = True
    wake_word_phrase: str = "jarvis"
    stt_model: str = "small.en"
    tts_model: str = "Kokoro-82M"
    audio_input_device_id: str = "default"
    audio_output_device_id: str = "default"
    renderer_model_preferred: str = "gemma4:e2b"
    renderer_model_fallback: str = "gemma4:e4b"
    vision_lite_model: str = "gemma4:e2b"
    vision_bg1_model: str = "qwen3-vl:8b"
    code_bg1_model: str = "deepcoder:14b"
    code_reviewer_model: str = "qwen2.5-coder:1.5b"
    logic_specialist_model: str = "deepseek-r1:8b"
    embedding_model: str = "nomic-embed-text-v2-moe"
    renderer_max_packet_tokens: int = 384
    conversation_buffer_max_turns: int = 8
    events_log_dir: str = "./logs"
    memory_backup_dir: str = "./backups"
    memory_db_path: str = ".jarvis_memory.sqlite"
    retry_backoff_base_ms: int = 400
    retry_backoff_max_ms: int = 3000
    degraded_announce_on_trigger: bool = True
    disallowed_uri_schemes: tuple[str, ...] = (
        "file",
        "ftp",
        "smb",
        "data",
        "chrome",
        "javascript",
    )
    permission_profiles: tuple[str, ...] = ("owner", "trusted", "guest")
    tool_first_target_min: float = 0.70
    tool_first_target_max: float = 0.85


def build_default_config() -> JarvisConfig:
    """Build config with JARVIS_* environment variable overrides.

    For each field on JarvisConfig, check for an environment variable named
    JARVIS_{FIELD_NAME} (uppercase). Supported types: str, int, float, bool, tuple[str].
    Bool accepts: 1/true/yes → True, 0/false/no → False.
    tuple[str] accepts comma-separated values.

    Example: JARVIS_RENDERER_MODEL_PREFERRED=llama3.2:3b
    """
    import os

    overrides: dict = {}
    for field_obj in JarvisConfig.__dataclass_fields__.values():
        env_key = f"JARVIS_{field_obj.name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is None:
            continue

        field_type = field_obj.type
        try:
            # Handle string-ified types from from __future__ import annotations
            if field_type == "int" or field_type is int:
                overrides[field_obj.name] = int(env_val)
            elif field_type == "float" or field_type is float:
                overrides[field_obj.name] = float(env_val)
            elif field_type == "bool" or field_type is bool:
                overrides[field_obj.name] = env_val.lower() in ("1", "true", "yes")
            elif "tuple" in str(field_type).lower():
                overrides[field_obj.name] = tuple(
                    v.strip() for v in env_val.split(",") if v.strip()
                )
            else:
                overrides[field_obj.name] = env_val
        except (ValueError, TypeError):
            continue  # Skip malformed env vars silently

    return JarvisConfig(**overrides)


def capability_map() -> dict[str, dict[str, bool]]:
    return {
        "owner": {
            "status": True,
            "memory_save": True,
            "route_control": True,
            "addon_control": True,
            "app_ops": True,
            "file_read": True,
            "file_write": True,
            "code_runner": True,
            "heavy_tasks": True,
            "cancel_heavy_task": True,
        },
        "trusted": {
            "status": True,
            "memory_save": True,
            "route_control": True,
            "addon_control": True,
            "app_ops": False,
            "file_read": True,
            "file_write": False,
            "code_runner": False,
            "heavy_tasks": True,
            "cancel_heavy_task": True,
        },
        "guest": {
            "status": True,
            "memory_save": False,
            "route_control": False,
            "addon_control": False,
            "app_ops": False,
            "file_read": False,
            "file_write": False,
            "code_runner": False,
            "heavy_tasks": False,
            "cancel_heavy_task": False,
        },
    }

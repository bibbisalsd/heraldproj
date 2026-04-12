from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..config import build_default_config
from ..ollama_runtime import resolve_ollama_bin


VOICE_DEPENDENCIES = ("faster_whisper", "kokoro", "sounddevice")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_model_name(model: str) -> str:
    return model.strip().lower()


def _model_base(model: str) -> str:
    return model.split(":", 1)[0]


def _is_model_available(
    model: str, installed_models: set[str], installed_bases: set[str]
) -> bool:
    normalized = _normalize_model_name(model)
    if normalized in installed_models:
        return True
    # Bare names should match any installed tagged variant (e.g. nomic-embed-text-v2-moe -> nomic-embed-text-v2-moe:latest)
    if ":" not in normalized and _model_base(normalized) in installed_bases:
        return True
    return False


def _parse_ollama_list(stdout: str) -> list[str]:
    models: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("NAME"):
            continue
        first_col = line.split()[0]
        if first_col:
            models.append(first_col)
    return _dedupe_preserve_order(models)


def _classify_ollama_error(stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}".lower()
    if "failed to create server log" in combined and "access is denied" in combined:
        return "ollama_log_permission_denied"
    if "timed out waiting for server to start" in combined:
        return "ollama_startup_timeout"
    return "ollama_list_failed"


def _kokoro_pack_available() -> bool:
    explicit_dir = Path(__file__).resolve().parents[1] / "voice" / "kokoro_pack"
    env_dir = Path(
        (os.getenv("JARVIS_KOKORO_PACK_DIR", "") or "").strip() or str(explicit_dir)
    ).expanduser()
    try:
        pack_dir = env_dir.resolve()
    except OSError:
        pack_dir = env_dir
    return (pack_dir / "jarvis_launcher.py").exists()


def list_installed_models(
    ollama_bin: str = "ollama", timeout_seconds: int = 20
) -> dict[str, object]:
    resolved_ollama_bin = resolve_ollama_bin(ollama_bin)
    try:
        completed = subprocess.run(
            [resolved_ollama_bin, "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "ollama_not_installed",
            "installed_models": [],
            "stdout": "",
            "stderr": "",
            "binary": resolved_ollama_bin,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "ollama_list_timeout",
            "installed_models": [],
            "stdout": "",
            "stderr": "",
            "binary": resolved_ollama_bin,
        }

    models = _parse_ollama_list(completed.stdout)
    if completed.returncode != 0:
        return {
            "ok": False,
            "error": _classify_ollama_error(completed.stdout, completed.stderr),
            "installed_models": models,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "binary": resolved_ollama_bin,
        }

    return {
        "ok": True,
        "error": None,
        "installed_models": models,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "binary": resolved_ollama_bin,
    }


def evaluate_model_readiness(
    required_models: list[str],
    optional_models: list[str] | None = None,
    ollama_bin: str = "ollama",
) -> dict[str, object]:
    required = _dedupe_preserve_order(required_models)
    optional = _dedupe_preserve_order(optional_models or [])

    listing = list_installed_models(ollama_bin=ollama_bin)
    installed = {
        _normalize_model_name(str(model)) for model in listing["installed_models"]
    }
    installed_bases = {_model_base(model) for model in installed}

    missing_required = [
        model
        for model in required
        if not _is_model_available(model, installed, installed_bases)
    ]
    missing_optional = [
        model
        for model in optional
        if not _is_model_available(model, installed, installed_bases)
    ]

    required_total = len(required)
    required_present = required_total - len(missing_required)
    required_coverage = (
        1.0 if required_total == 0 else required_present / required_total
    )

    return {
        "status": "ready" if listing["ok"] and not missing_required else "not_ready",
        "ollama": {
            "binary": str(listing.get("binary", ollama_bin)),
            "ok": bool(listing["ok"]),
            "error": listing["error"],
        },
        "models": {
            "required": required,
            "optional": optional,
            "installed": sorted(installed),
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "required_coverage": round(required_coverage, 3),
        },
    }


def evaluate_voice_dependency_readiness(
    dependencies: tuple[str, ...] = VOICE_DEPENDENCIES,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    missing: list[str] = []

    for dependency in dependencies:
        available = importlib.util.find_spec(dependency) is not None
        pack_available = False
        satisfied = available
        if dependency == "kokoro":
            pack_available = _kokoro_pack_available()
            satisfied = available or pack_available
            checks.append(
                {
                    "name": dependency,
                    "available": available,
                    "pack_available": pack_available,
                    "satisfied": satisfied,
                }
            )
        else:
            checks.append({"name": dependency, "available": available})
        if not satisfied:
            missing.append(dependency)

    if not missing:
        status = "ready"
    elif len(missing) == len(dependencies):
        status = "not_ready"
    else:
        status = "partial"

    return {
        "status": status,
        "checks": checks,
        "missing": missing,
    }


def build_readiness_report(
    include_voice: bool = True,
    require_voice: bool = False,
    ollama_bin: str = "ollama",
) -> dict[str, object]:
    cfg = build_default_config()
    model_report = evaluate_model_readiness(
        required_models=[
            cfg.renderer_model_preferred,
            cfg.renderer_model_fallback,
            cfg.vision_lite_model,
            cfg.vision_bg1_model,
            cfg.code_bg1_model,
            cfg.embedding_model,
        ],
        optional_models=[],
        ollama_bin=ollama_bin,
    )

    voice_report: dict[str, object] | None = None
    if include_voice:
        voice_report = evaluate_voice_dependency_readiness()

    overall_status = "ready"
    blockers: list[str] = []
    recommendations: list[str] = []

    if model_report["status"] != "ready":
        overall_status = "not_ready"
        blockers.append("required_models_missing")
        import platform

        if platform.system() == "Windows":
            recommendations.append(
                "Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_models.ps1 -PullMissingOnly"
            )
        else:
            recommendations.append(
                "Run: bash scripts/verify_gpu.sh && ollama pull <model-name> for each missing model"
            )
        if model_report["ollama"]["error"] == "ollama_log_permission_denied":
            if platform.system() == "Windows":
                recommendations.append(
                    "Ollama cannot write to %LOCALAPPDATA%\\Ollama\\app.log in this session. "
                    "Fix permissions or launch Ollama under the current user context."
                )
            else:
                recommendations.append(
                    "Ollama log permission denied. Check ~/.ollama/ permissions "
                    "or run: sudo chown -R $USER ~/.ollama"
                )

    if (
        include_voice
        and voice_report is not None
        and require_voice
        and voice_report["status"] != "ready"
    ):
        overall_status = "not_ready"
        blockers.append("voice_dependencies_missing")
        recommendations.append(
            "Install optional voice deps: pip install -r requirements-voice.txt"
        )
    elif (
        include_voice and voice_report is not None and voice_report["status"] != "ready"
    ):
        recommendations.append(
            "Voice backends are optional. Install with: pip install -r requirements-voice.txt"
        )

    return {
        "timestamp": _utc_now_iso(),
        "overall_status": overall_status,
        "blockers": blockers,
        "models": model_report,
        "voice": voice_report,
        "recommendations": recommendations,
    }


def render_readiness_report(report: dict[str, object]) -> str:
    models = report["models"]
    model_payload = models["models"]

    lines = [
        f"overall_status: {report['overall_status']}",
        f"timestamp_utc: {report['timestamp']}",
        f"ollama_ok: {models['ollama']['ok']}",
        f"required_model_coverage: {model_payload['required_coverage']}",
        "missing_required_models: " + ", ".join(model_payload["missing_required"])
        if model_payload["missing_required"]
        else "missing_required_models: none",
        "missing_optional_models: " + ", ".join(model_payload["missing_optional"])
        if model_payload["missing_optional"]
        else "missing_optional_models: none",
    ]

    voice_payload = report.get("voice")
    if isinstance(voice_payload, dict):
        lines.append(f"voice_status: {voice_payload['status']}")
        missing_voice = voice_payload.get("missing", [])
        if missing_voice:
            lines.append(
                "missing_voice_dependencies: "
                + ", ".join(str(item) for item in missing_voice)
            )
        else:
            lines.append("missing_voice_dependencies: none")

    blockers = report.get("blockers", [])
    lines.append(
        "blockers: "
        + (", ".join(str(item) for item in blockers) if blockers else "none")
    )

    recommendations = report.get("recommendations", [])
    if recommendations:
        lines.append("recommendations:")
        for item in recommendations:
            lines.append(f"- {item}")
    else:
        lines.append("recommendations: none")

    return "\n".join(lines)


def to_json(report: dict[str, object]) -> str:
    return json.dumps(report, indent=2)

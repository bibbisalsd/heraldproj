from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from jarvis.maintenance.model_readiness import (
    build_readiness_report,
    evaluate_model_readiness,
    evaluate_voice_dependency_readiness,
)


def test_evaluate_model_readiness_when_ollama_missing(monkeypatch) -> None:
    def _raise_missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("jarvis.maintenance.model_readiness.subprocess.run", _raise_missing)

    report = evaluate_model_readiness(required_models=["llama3.2:1b"])
    assert report["status"] == "not_ready"
    assert report["ollama"]["ok"] is False
    assert report["ollama"]["error"] == "ollama_not_installed"
    assert report["models"]["missing_required"] == ["llama3.2:1b"]


def test_evaluate_model_readiness_parses_models(monkeypatch) -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout=(
            "NAME                 ID              SIZE      MODIFIED\n"
            "llama3.2:1b          deadbeef1234    1.9 GB    2 days ago\n"
            "deepcoder:14b        feedface5678    8.1 GB    5 days ago\n"
        ),
        stderr="",
    )
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    report = evaluate_model_readiness(
        required_models=["llama3.2:1b", "deepcoder:14b"],
        optional_models=["nomic-embed-text-v2-moe"],
    )
    assert report["status"] == "ready"
    assert report["models"]["missing_required"] == []
    assert report["models"]["missing_optional"] == ["nomic-embed-text-v2-moe"]
    assert report["models"]["required_coverage"] == 1.0


def test_evaluate_model_readiness_bare_optional_matches_tagged_install(monkeypatch) -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout=(
            "NAME                      ID              SIZE      MODIFIED\n"
            "llama3.2:1b               deadbeef1234    1.9 GB    2 days ago\n"
            "nomic-embed-text-v2-moe:latest   feedface5678    0.9 GB    1 day ago\n"
        ),
        stderr="",
    )
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    report = evaluate_model_readiness(
        required_models=["llama3.2:1b"],
        optional_models=["nomic-embed-text-v2-moe"],
    )
    assert report["status"] == "ready"
    assert report["models"]["missing_required"] == []
    assert report["models"]["missing_optional"] == []


def test_evaluate_voice_dependency_readiness(monkeypatch) -> None:
    available = {"faster_whisper"}
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.importlib.util.find_spec",
        lambda name: object() if name in available else None,
    )
    monkeypatch.setattr("jarvis.maintenance.model_readiness._kokoro_pack_available", lambda: False)

    report = evaluate_voice_dependency_readiness()
    assert report["status"] == "partial"
    assert "kokoro" in report["missing"]
    assert "sounddevice" in report["missing"]


def test_evaluate_voice_dependency_readiness_accepts_kokoro_pack(monkeypatch) -> None:
    available = {"sounddevice"}
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.importlib.util.find_spec",
        lambda name: object() if name in available else None,
    )
    monkeypatch.setattr("jarvis.maintenance.model_readiness._kokoro_pack_available", lambda: True)

    report = evaluate_voice_dependency_readiness()
    kokoro = next(item for item in report["checks"] if item["name"] == "kokoro")

    assert report["status"] == "partial"
    assert "kokoro" not in report["missing"]
    assert "faster_whisper" in report["missing"]
    assert kokoro["available"] is False
    assert kokoro["pack_available"] is True
    assert kokoro["satisfied"] is True


def test_build_readiness_report_require_voice_can_block(monkeypatch) -> None:
    completed = SimpleNamespace(returncode=0, stdout="NAME\nllama3.2:1b 123\n", stderr="")
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.subprocess.run",
        lambda *args, **kwargs: completed,
    )
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.importlib.util.find_spec",
        lambda name: None,
    )

    report = build_readiness_report(include_voice=True, require_voice=True)
    assert report["overall_status"] == "not_ready"
    assert "voice_dependencies_missing" in report["blockers"]
    assert "required_models_missing" in report["blockers"]


def test_build_readiness_report_treats_embedding_model_as_required(monkeypatch) -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout=(
            "NAME\n"
            "llama3.2:1b 123\n"
            "llama3.2:3b 456\n"
            "qwen2.5vl:3b 789\n"
            "qwen3-vl:8b abc\n"
            "deepcoder:14b def\n"
        ),
        stderr="",
    )
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.subprocess.run",
        lambda *args, **kwargs: completed,
    )
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.importlib.util.find_spec",
        lambda name: object(),
    )
    monkeypatch.setattr("jarvis.maintenance.model_readiness._kokoro_pack_available", lambda: True)

    report = build_readiness_report(include_voice=True, require_voice=False)

    assert report["overall_status"] == "not_ready"
    assert "required_models_missing" in report["blockers"]
    # All core models are required if not present
    assert "gemma4:e2b" in report["models"]["models"]["missing_required"]
    assert "gemma4:e4b" in report["models"]["models"]["missing_required"]
    assert "nomic-embed-text-v2-moe" in report["models"]["models"]["missing_required"]
    assert report["models"]["models"]["missing_optional"] == []


def test_list_timeout_maps_to_not_ready(monkeypatch) -> None:
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["ollama", "list"], timeout=20)

    monkeypatch.setattr("jarvis.maintenance.model_readiness.subprocess.run", _raise_timeout)

    report = evaluate_model_readiness(required_models=["llama3.2:1b"])
    assert report["status"] == "not_ready"
    assert report["ollama"]["error"] == "ollama_list_timeout"


def test_list_permission_denied_is_classified(monkeypatch) -> None:
    completed = SimpleNamespace(
        returncode=1,
        stdout='ERROR failed to create server log open C:\\Users\\x\\AppData\\Local\\Ollama\\app.log: Access is denied.',
        stderr="Error: timed out waiting for server to start",
    )
    monkeypatch.setattr(
        "jarvis.maintenance.model_readiness.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    report = evaluate_model_readiness(required_models=["llama3.2:1b"])
    assert report["status"] == "not_ready"
    assert report["ollama"]["error"] == "ollama_log_permission_denied"

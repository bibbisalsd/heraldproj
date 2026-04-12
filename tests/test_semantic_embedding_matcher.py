from __future__ import annotations

from types import SimpleNamespace

from jarvis.brain_core.semantic_command_match import SemanticCommandMatcher


def _fake_embed(text: str) -> list[float] | None:
    lowered = text.lower()
    if any(token in lowered for token in ("time", "clock", "hour")):
        return [1.0, 0.0, 0.0]
    if any(token in lowered for token in ("status", "progress", "update", "doing", "busy", "workload")):
        return [0.0, 1.0, 0.0]
    if any(token in lowered for token in ("cancel", "abort", "terminate", "stop", "kill")):
        return [0.0, 0.0, 1.0]
    if any(token in lowered for token in ("free", "done", "finished", "available")):
        return [0.0, 1.0, 0.2]
    return None


def test_embedding_matcher_can_classify_when_lexical_is_weak() -> None:
    matcher = SemanticCommandMatcher(
        enable_embeddings=True,
        embedding_threshold=0.5,
        embedder=_fake_embed,
    )

    result = matcher.match("how is the workload going")
    assert result.intent == "job_status"
    assert result.score >= 0.5


def test_embedding_failure_falls_back_to_lexical() -> None:
    matcher = SemanticCommandMatcher(
        enable_embeddings=True,
        embedder=lambda _text: None,
    )

    result = matcher.match("show me the time")
    assert result.intent == "time_query"
    assert result.score >= 0.5


def test_embeddings_disabled_preserves_existing_behavior() -> None:
    calls = {"count": 0}

    def counting_embed(_text: str) -> list[float] | None:
        calls["count"] += 1
        return [1.0, 0.0, 0.0]

    matcher = SemanticCommandMatcher(enable_embeddings=False, embedder=counting_embed)
    result = matcher.match("show me the time")

    assert result.intent == "time_query"
    assert calls["count"] == 0


def test_embeddings_are_enabled_by_default_when_env_is_unset(monkeypatch) -> None:
    calls: list[str] = []

    class FakeClient:
        def __init__(self, model: str, **kwargs) -> None:
            self.model = model

        def embed(self, text: str) -> SimpleNamespace:
            calls.append(text)
            return SimpleNamespace(ok=True, vector=[1.0, 0.0, 0.0])

    monkeypatch.delenv("JARVIS_ENABLE_EMBEDDING_MATCH", raising=False)
    monkeypatch.setattr(
        "jarvis.brain_core.semantic_command_match.OllamaEmbeddingClient",
        FakeClient,
    )

    matcher = SemanticCommandMatcher(
        enable_embeddings=None,
        embedding_model="nomic-embed-text-v2-moe",
    )
    matcher.match("show me the time")

    assert any(call.startswith("search_query: ") for call in calls)
    assert any(call.startswith("search_document: ") for call in calls)


def test_nomic_v2_moe_uses_query_and_document_prefixes(monkeypatch) -> None:
    calls: list[str] = []

    class FakeClient:
        def __init__(self, model: str, **kwargs) -> None:
            self.model = model

        def embed(self, text: str) -> SimpleNamespace:
            calls.append(text)
            return SimpleNamespace(ok=True, vector=[1.0, 0.0, 0.0])

    monkeypatch.setattr(
        "jarvis.brain_core.semantic_command_match.OllamaEmbeddingClient",
        FakeClient,
    )

    matcher = SemanticCommandMatcher(
        enable_embeddings=True,
        embedding_model="nomic-embed-text-v2-moe",
    )
    matcher.match("show me the time")

    assert any(call.startswith("search_query: ") for call in calls)
    assert any(call.startswith("search_document: ") for call in calls)

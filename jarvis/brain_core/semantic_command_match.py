from __future__ import annotations

import math
import os
from dataclasses import dataclass
import threading
from functools import lru_cache
from typing import Callable

from ..models.embedding import OllamaEmbeddingClient

SYNONYMS: dict[str, str] = {
    "show": "what",
    "tell": "what",
    "give": "what",
    "display": "what",
    "check": "what",
    "clock": "time",
    "hour": "time",
    "doing": "doing",
    "working": "doing",
    "running": "doing",
    "happening": "doing",
    "processing": "doing",
    "progress": "status",
    "update": "status",
    "stop": "cancel",
    "abort": "cancel",
    "kill": "cancel",
    "halt": "cancel",
    "terminate": "cancel",
    "activate": "enable",
    "deactivate": "disable",
    "start": "enable",
    "on": "enable",
    "off": "disable",
    "job": "task",
    "work": "task",
    "process": "task",
    "occupied": "busy",
    "available": "free",
    "done": "free",
    "finished": "free",
    "complete": "free",
    "idle": "free",
}


INTENT_PHRASES = {
    "job_status": {
        "status",
        "what are you doing",
        "how are you doing",
        "notify me when free",
        "what are you doing right now",
        "are you busy",
        "whats happening",
        "any progress",
        "hows it going",
        "give me an update",
        "whats going on",
    },
    "job_cancel": {
        "cancel current heavy task",
        "stop heavy task",
        "cancel heavy",
        "stop what youre doing",
        "abort task",
        "kill the task",
    },
    "bg1_result": {
        "tell me the result from the last heavy task",
        "tell me the result from the background task",
        "what did the background task find",
        "what were the results",
        "did the background task finish",
        "tell me the result from analysis",
        "what is the background task result",
        "what did you find out",
    },
    "notify_when_free": {
        "notify me when free",
        "tell me when free",
        "let me know when free",
        "tell me when done",
        "let me know when finished",
        "ping me when available",
    },
    "time_query": {
        "what time is it",
        "whats the time",
        "current time",
        "show me the time",
        "tell me the time",
        "give me the time",
        "check the time",
        "what is the current time",
    },
    "day_query": {
        "what day is it",
        "what day is today",
        "what weekday is it",
        "tell me the day",
        "give me the day",
    },
    "date_query": {
        "what date is it",
        "what is the date",
        "what is today's date",
        "give me today's date",
        "what day of the month is it",
    },
    "addon_enable": {"enable addon", "turn addon on", "activate addon", "start addon"},
    "addon_disable": {
        "disable addon",
        "turn addon off",
        "deactivate addon",
        "stop addon",
    },
    "self_query": {
        "where is your code",
        "what is your source code",
        "show me your source",
        "where do you keep your files",
    },
    "codebase_query": {
        "do you know your code base",
        "tell me about your codebase",
        "describe your source code",
        "how are you built",
    },
}


@dataclass(frozen=True)
class MatchResult:
    intent: str | None
    score: float


def _token_set(text: str) -> set[str]:
    return {token for token in text.lower().split() if token}


def _expand_synonyms(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        if token in SYNONYMS:
            expanded.add(SYNONYMS[token])
    return expanded


def _bigrams(tokens: list[str]) -> set[str]:
    if len(tokens) < 2:
        return set()
    return {f"{tokens[index]}_{tokens[index + 1]}" for index in range(len(tokens) - 1)}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticEmbeddingMatcher:
    """Optional embedding matcher that maps user text to known intent phrases."""

    def __init__(
        self,
        embed_query: Callable[[str], list[float] | None],
        threshold: float = 0.62,
        embed_document: Callable[[str], list[float] | None] | None = None,
    ) -> None:
        self._embed_query = embed_query
        self._embed_document = embed_document or embed_query
        self._threshold = threshold
        self._phrase_vectors: dict[str, list[tuple[str, list[float]]]] = {}
        self._vectors_lock = threading.Lock()

        # Pre-compute vectors in background thread
        threading.Thread(target=self._precompute, daemon=True).start()

    def _precompute(self) -> None:
        self._ensure_phrase_vectors()

    @lru_cache(maxsize=200)
    def _cached_embed(self, text: str) -> list[float] | None:
        return self._embed_query(text)

    def match(self, text: str) -> MatchResult:
        query_vector = self._cached_embed(text)
        if not query_vector:
            return MatchResult(intent=None, score=0.0)

        best_intent: str | None = None
        best_score = 0.0

        with self._vectors_lock:
            if not self._phrase_vectors:
                # Force synchronous initialization if background thread hasn't finished
                vectors_map = self._ensure_phrase_vectors()
            else:
                vectors_map = self._phrase_vectors

        for intent, phrase_vectors in vectors_map.items():
            for _, phrase_vector in phrase_vectors:
                score = _cosine_similarity(query_vector, phrase_vector)
                if score > best_score:
                    best_score = score
                    best_intent = intent

        if best_score < self._threshold:
            return MatchResult(intent=None, score=best_score)
        return MatchResult(intent=best_intent, score=best_score)

    def _ensure_phrase_vectors(self) -> dict[str, list[tuple[str, list[float]]]]:
        with self._vectors_lock:
            if self._phrase_vectors:
                return self._phrase_vectors

        vectors_map: dict[str, list[tuple[str, list[float]]]] = {}
        for intent, phrases in INTENT_PHRASES.items():
            vectors: list[tuple[str, list[float]]] = []
            for phrase in phrases:
                vector = self._embed_document(phrase)
                if vector:
                    vectors.append((phrase, vector))
            vectors_map[intent] = vectors

        with self._vectors_lock:
            if not self._phrase_vectors:
                self._phrase_vectors = vectors_map
            return self._phrase_vectors


class SemanticCommandMatcher:
    def __init__(
        self,
        enable_embeddings: bool | None = None,
        embedding_model: str = "nomic-embed-text-v2-moe",
        embedding_threshold: float = 0.62,
        lexical_threshold: float = 0.5,
        embedder: Callable[[str], list[float] | None] | None = None,
    ) -> None:
        if enable_embeddings is None:
            raw = os.getenv("JARVIS_ENABLE_EMBEDDING_MATCH", "true").strip().lower()
            enable_embeddings = raw not in {"0", "false", "no", "off"}
        self._lexical_threshold = lexical_threshold
        self._embedding_matcher: SemanticEmbeddingMatcher | None = None

        if enable_embeddings:
            if embedder is not None:
                embed_query_fn = embedder
                embed_document_fn = embedder
            else:
                client = OllamaEmbeddingClient(model=embedding_model, timeout_seconds=2)
                normalized_model = embedding_model.strip().lower().split(":", 1)[0]
                use_nomic_v2_prefixes = normalized_model == "nomic-embed-text-v2-moe"

                def _embed_with_prefix(
                    text: str, prefix: str = ""
                ) -> list[float] | None:
                    cleaned = text.strip()
                    payload = f"{prefix}{cleaned}" if prefix and cleaned else cleaned
                    result = client.embed(payload)
                    return result.vector if result.ok else None

                def embed_query_fn(text: str) -> list[float] | None:
                    prefix = "search_query: " if use_nomic_v2_prefixes else ""
                    return _embed_with_prefix(text, prefix)

                def embed_document_fn(text: str) -> list[float] | None:
                    prefix = "search_document: " if use_nomic_v2_prefixes else ""
                    return _embed_with_prefix(text, prefix)

            self._embedding_matcher = SemanticEmbeddingMatcher(
                embed_query=embed_query_fn,
                embed_document=embed_document_fn,
                threshold=embedding_threshold,
            )

    @lru_cache(maxsize=128)
    def match(self, text: str) -> MatchResult:
        lexical = self._match_lexical(text)
        if self._embedding_matcher is None:
            return lexical

        embedding = self._embedding_matcher.match(text)
        if embedding.intent is not None and (
            lexical.intent is None or embedding.score >= lexical.score
        ):
            return embedding
        return lexical

    def _match_lexical(self, text: str) -> MatchResult:
        text_token_list = [token for token in text.lower().split() if token]
        text_tokens = _expand_synonyms(set(text_token_list))
        text_bigrams = _bigrams(text_token_list)

        best_intent: str | None = None
        best_score = 0.0

        for intent, phrases in INTENT_PHRASES.items():
            for phrase in phrases:
                phrase_token_list = [token for token in phrase.lower().split() if token]
                phrase_tokens = _expand_synonyms(set(phrase_token_list))
                phrase_bigrams = _bigrams(phrase_token_list)

                uni_overlap = len(text_tokens & phrase_tokens)
                uni_total = max(1, len(phrase_tokens))

                bi_overlap = len(text_bigrams & phrase_bigrams)
                bi_total = len(phrase_bigrams)

                if bi_total > 0:
                    score = (uni_overlap + 1.5 * bi_overlap) / (
                        uni_total + 1.5 * bi_total
                    )
                else:
                    score = uni_overlap / uni_total

                if score > best_score:
                    best_score = score
                    best_intent = intent

        if best_score < self._lexical_threshold:
            return MatchResult(intent=None, score=best_score)
        return MatchResult(intent=best_intent, score=best_score)

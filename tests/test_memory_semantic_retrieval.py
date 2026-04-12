from __future__ import annotations

from jarvis.memory import Memory
from jarvis.tools import memory_tool


def _fake_embed_query(text: str) -> list[float] | None:
    lowered = text.lower()
    if "noodle" in lowered or "ramen" in lowered:
        return [1.0, 0.0, 0.0]
    if "cat" in lowered or "pet" in lowered:
        return [0.0, 1.0, 0.0]
    return None


def _fake_embed_document(text: str) -> list[float] | None:
    lowered = text.lower()
    if "ramen" in lowered:
        return [1.0, 0.0, 0.0]
    if "cat" in lowered or "milo" in lowered:
        return [0.0, 1.0, 0.0]
    return None


def test_memory_search_can_return_semantic_matches(tmp_path) -> None:
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    assert memory.remember("favorite_food", "spicy ramen", confidence=0.95) is True
    assert memory.remember("pet_name", "Milo the cat", confidence=0.95) is True

    rows = memory.search(
        "which noodles do I like",
        enable_semantic=True,
        embed_query=_fake_embed_query,
        embed_document=_fake_embed_document,
    )

    assert rows
    assert rows[0].value == "spicy ramen"
    assert rows[0].match_type == "semantic"
    assert rows[0].score >= 0.95


def test_memory_search_keeps_exact_key_matches_first(tmp_path) -> None:
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    assert memory.remember("favorite_food", "spicy ramen", confidence=0.95) is True
    assert memory.remember("food_note", "ramen is the best", confidence=0.95) is True

    rows = memory.search(
        "favorite_food",
        enable_semantic=True,
        embed_query=_fake_embed_query,
        embed_document=_fake_embed_document,
    )

    assert rows
    assert rows[0].key == "favorite_food"
    assert rows[0].match_type == "exact"
    assert rows[0].score == 1.0


def test_memory_search_caches_document_embeddings(tmp_path) -> None:
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    assert memory.remember("favorite_food", "spicy ramen", confidence=0.95) is True

    calls = {"document": 0}

    def counting_embed_document(text: str) -> list[float] | None:
        calls["document"] += 1
        return _fake_embed_document(text)

    first = memory.search(
        "ramen",
        enable_semantic=True,
        embed_query=_fake_embed_query,
        embed_document=counting_embed_document,
    )
    second = memory.search(
        "ramen",
        enable_semantic=True,
        embed_query=_fake_embed_query,
        embed_document=counting_embed_document,
    )

    assert first
    assert second
    assert calls["document"] == 1


def test_memory_tool_retrieve_returns_match_metadata(tmp_path) -> None:
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    assert memory.remember("favorite_food", "spicy ramen", confidence=0.95) is True

    original_search = memory.search

    def fake_search(query: str, top_k: int = 6, **kwargs):
        del kwargs
        return original_search(
            query,
            top_k=top_k,
            enable_semantic=True,
            embed_query=_fake_embed_query,
            embed_document=_fake_embed_document,
        )

    memory.search = fake_search  # type: ignore[method-assign]
    payload = memory_tool.retrieve(memory, "noodles", top_k=3)

    assert payload["items"] == ["spicy ramen"]
    assert payload["count"] == 1
    assert payload["matches"][0]["match_type"] == "semantic"
    assert payload["matches"][0]["score"] >= 0.95

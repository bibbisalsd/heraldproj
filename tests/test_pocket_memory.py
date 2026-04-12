from __future__ import annotations

from jarvis.memory import Memory


def test_memory_seeds_core_protected_pockets(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    self_pocket = memory.pockets.get_entity("self:jarvis")
    codebase_pocket = memory.pockets.get_entity("codebase:jarviscore")
    persona_tone = memory.pockets.get_slot("persona:jarvis", "tone")
    calculator_tool = memory.pockets.get_entity("tool:calculator")
    voice_runtime_module = memory.pockets.get_entity("module:voice_runtime")

    assert self_pocket is not None
    assert self_pocket.protection_level == "canonical"
    assert codebase_pocket is not None
    assert codebase_pocket.canonical_name == "Jarviscore"
    assert calculator_tool is not None
    assert voice_runtime_module is not None
    assert persona_tone is not None
    assert persona_tone.slot_value == "concise_direct_calm"
    assert persona_tone.protection_level == "canonical"


def test_memory_protects_canonical_slots_from_conversational_overwrite(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    changed = memory.pockets.set_slot(
        "self:jarvis",
        "name",
        "Not Jarvis",
        provenance_type="conversation",
        source="user_text",
        protection_level="dynamic",
    )

    current = memory.pockets.get_slot("self:jarvis", "name")
    assert changed is False
    assert current is not None
    assert current.slot_value == "Jarvis"


def test_user_name_syncs_into_owner_pocket(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    assert memory.remember_latest("user_name", "James", confidence=0.95) is True

    owner = memory.pockets.get_entity("person:owner")
    owner_name = memory.pockets.get_slot("person:owner", "name")
    owner_links = memory.pockets.related_entity_ids("person:owner")

    assert owner is not None
    assert owner.canonical_name == "James"
    assert owner_name is not None
    assert owner_name.slot_value == "James"
    assert "self:jarvis" in owner_links


def test_user_profile_slots_share_owner_pocket(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    memory.remember_latest("user_name", "James", confidence=0.95)
    memory.remember_latest("user_address_preference", "James", confidence=0.95)
    memory.remember_latest("user_age", "32", confidence=0.95)

    address = memory.pockets.get_slot("person:owner", "address_preference")
    age = memory.pockets.get_slot("person:owner", "age")

    assert address is not None
    assert address.slot_value == "James"
    assert age is not None
    assert age.slot_value == "32"
    assert age.value_type == "integer"


def test_pocket_reference_resolution_and_shortcuts(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    assert memory.pockets.resolve_reference("me") == "person:owner"
    assert memory.pockets.resolve_reference("Jarvis") == "self:jarvis"
    assert memory.pockets.resolve_reference("your codebase") == "codebase:jarviscore"

    related = memory.pockets.relevant_entity_ids("self:jarvis")
    assert "self:jarvis" in related
    assert "project:jarvis" in related
    assert "codebase:jarviscore" in related


def test_memory_seeds_creator_and_architecture_pockets(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))

    james = memory.pockets.get_entity("person:creator_james")
    bxserkk = memory.pockets.get_entity("person:creator_bxserkk")
    architecture = memory.pockets.get_entity("architecture:herald_skeptic")
    creator_link_targets = memory.pockets.related_entity_ids("self:jarvis")

    assert james is not None
    assert bxserkk is not None
    assert architecture is not None
    assert "person:creator_james" in creator_link_targets
    assert "person:creator_bxserkk" in creator_link_targets
    assert "architecture:herald_skeptic" in creator_link_targets

    assert memory.pockets.get_slot("person:creator_james", "handle").slot_value == "gxzx"
    assert memory.pockets.get_slot("person:creator_bxserkk", "spoken_name").slot_value == "berserk"


def test_memory_wipe_dynamic_preserves_protected_jarvis_core(tmp_path):
    memory = Memory(db_path=str(tmp_path / "memory.sqlite"))
    memory.remember_latest("user_name", "James", confidence=0.95)
    memory.remember_latest("user_age", "32", confidence=0.95)

    result = memory.wipe_dynamic_memory(backup_dir=str(tmp_path / "backups"))

    assert result["backup_path"]
    assert memory.owner_name() is None
    assert memory.recall("user_name") == []
    assert memory.pockets.get_entity("self:jarvis") is not None
    assert memory.pockets.get_entity("person:creator_james") is not None
    assert memory.pockets.get_entity("person:owner") is None

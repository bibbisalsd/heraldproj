"""Discord permission mapping.

Phase 4E: Discord Completion
- Map Discord user roles to Harold profiles (owner/trusted/guest)
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Set


# Cached owner/trusted Discord user IDs
_OWNER_IDS: Set[str] = set()
_TRUSTED_IDS: Set[str] = set()
_initialized = False


def _init_config() -> None:
    """Initialize permission config from environment."""
    global _OWNER_IDS, _TRUSTED_IDS, _initialized

    if _initialized:
        return

    # Parse Discord user IDs from environment
    owner_ids = os.environ.get("DISCORD_OWNER_IDS", "")
    trusted_ids = os.environ.get("DISCORD_TRUSTED_IDS", "")

    _OWNER_IDS = {id.strip() for id in owner_ids.split(",") if id.strip()}
    _TRUSTED_IDS = {id.strip() for id in trusted_ids.split(",") if id.strip()}
    _initialized = True


def map_identity_to_profile(identity: str) -> str:
    """Map Discord identity to Harold profile.

    Identity format: "discord:<user_id>" or just "<user_id>"

    Returns:
        "owner" - Full access, can control addon
        "trusted" - Extended access, can use most features
        "guest" - Limited access, basic queries only
    """
    _init_config()

    # Extract user ID from identity
    user_id = identity
    if identity.startswith("discord:"):
        user_id = identity[8:]
    elif identity.startswith("author_id:"):
        user_id = identity[10:]

    # Check ownership
    if user_id in _OWNER_IDS:
        return "owner"

    # Check trusted
    if user_id in _TRUSTED_IDS:
        return "trusted"

    # Default to guest
    return "guest"


def configure_owners(owner_ids: Set[str]) -> None:
    """Configure owner Discord user IDs."""
    global _OWNER_IDS, _initialized
    _OWNER_IDS = owner_ids
    _initialized = True


def configure_trusted(trusted_ids: Set[str]) -> None:
    """Configure trusted Discord user IDs."""
    global _TRUSTED_IDS, _initialized
    _TRUSTED_IDS = trusted_ids
    _initialized = True


def get_permission_config() -> Dict[str, Set[str]]:
    """Get current permission configuration."""
    _init_config()
    return {
        "owners": _OWNER_IDS.copy(),
        "trusted": _TRUSTED_IDS.copy(),
    }

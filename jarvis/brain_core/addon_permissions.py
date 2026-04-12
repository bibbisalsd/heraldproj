from __future__ import annotations


class AddonPermissionMapper:
    def __init__(self) -> None:
        self._map: dict[str, str] = {}

    def register_identity(self, identity: str, profile: str) -> None:
        self._map[identity] = profile

    def resolve_profile(self, identity: str) -> str:
        return self._map.get(identity, "guest")

"""UserProfile - Track user preferences, verification status, and interaction history."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class UserProfile:
    """User profile tracking preferences and interaction history."""

    user_id: str = "default"
    preferences: dict[str, str] = field(default_factory=dict)
    verification_status: str = "unverified"  # "unverified", "verified", "trusted"
    interaction_history: list[dict] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def with_preference(self, key: str, value: str) -> "UserProfile":
        """Create a new UserProfile with an added/updated preference."""
        new_prefs = dict(self.preferences)
        new_prefs[key] = value
        return UserProfile(
            user_id=self.user_id,
            preferences=new_prefs,
            verification_status=self.verification_status,
            interaction_history=self.interaction_history,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def with_verification_status(self, status: str) -> "UserProfile":
        """Create a new UserProfile with updated verification status."""
        valid_statuses = {"unverified", "verified", "trusted"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid verification status: {status}. Must be one of {valid_statuses}"
            )
        return UserProfile(
            user_id=self.user_id,
            preferences=self.preferences,
            verification_status=status,
            interaction_history=self.interaction_history,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def add_interaction(self, interaction: dict) -> "UserProfile":
        """Create a new UserProfile with an added interaction record."""
        new_history = list(self.interaction_history)
        new_history.append(
            {
                **interaction,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        # Keep only last 100 interactions
        if len(new_history) > 100:
            new_history = new_history[-100:]
        return UserProfile(
            user_id=self.user_id,
            preferences=self.preferences,
            verification_status=self.verification_status,
            interaction_history=new_history,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

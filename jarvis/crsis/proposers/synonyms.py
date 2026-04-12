"""SynonymProposer - Propose new synonym mappings."""

from __future__ import annotations


from typing import Any


class SynonymProposer:
    """Propose new synonym mappings for semantic command matching.

    Analyzes misrouting patterns where semantic matching failed
    and suggests new synonym entries.
    """

    def __init__(self) -> None:
        # Common synonym patterns
        self._synonym_categories = {
            "start": ["begin", "launch", "initiate", "run", "execute"],
            "stop": ["halt", "terminate", "end", "cancel", "abort"],
            "show": ["display", "list", "view", "see", "check"],
            "create": ["make", "add", "new", "generate", "build"],
            "delete": ["remove", "drop", "clear", "erase", "destroy"],
            "update": ["change", "modify", "edit", "set", "fix"],
            "help": ["assist", "support", "guide", "explain"],
        }

    def propose(self, pattern: Any) -> dict[str, Any] | None:
        """Generate a synonym proposal from a pattern.

        Args:
            pattern: PatternFinding with misrouting data

        Returns:
            Proposal dict or None if no proposal generated
        """
        if pattern.pattern_type != "misrouting":
            return None

        # Extract intent from affected_component
        component = pattern.affected_component
        if ":" in component:
            _, intent = component.split(":", 1)
        else:
            intent = "unknown"

        # Extract candidate synonym from examples
        candidate = self._extract_candidate(pattern.examples, intent)
        if not candidate:
            return None

        # Find matching category
        category = self._find_category(candidate)
        if not category:
            return None

        return {
            "target_file": "jarvis/brain_core/semantic_command_match.py",
            "target_structure": "SYNONYM_MAPPINGS",
            "proposed_change": {
                "category": category,
                "intent": intent,
                "synonym": candidate,
            },
            "expected_impact": f"Add '{candidate}' as synonym for '{category}' → '{intent}'",
            "rollback_path": f"Remove '{candidate}' from SYNONYM_MAPPINGS['{category}']",
        }

    def _extract_candidate(self, examples: list[str], intent: str) -> str | None:
        """Extract candidate synonym from examples."""
        for example in examples:
            # Look for words that might be the misrouted phrase
            words = example.lower().replace("'", "").replace('"', "").split()
            for word in words:
                # Skip common words
                if word in ("the", "a", "is", "was", "to", "of", "and", "or"):
                    continue
                if len(word) >= 3:
                    return word
        return None

    def _find_category(self, candidate: str) -> str | None:
        """Find the synonym category for a candidate word."""
        candidate_lower = candidate.lower()
        for category, synonyms in self._synonym_categories.items():
            if candidate_lower in synonyms:
                return category
        return None

    def add_synonym_category(self, category: str, synonyms: list[str]) -> None:
        """Add a new synonym category."""
        self._synonym_categories[category] = synonyms

    def get_categories(self) -> list[str]:
        """Get all synonym categories."""
        return list(self._synonym_categories.keys())

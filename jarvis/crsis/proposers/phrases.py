"""PhraseProposer - Propose new exact-match phrases."""

from __future__ import annotations


from typing import Any


class PhraseProposer:
    """Propose new exact-match phrases for intent routing.

    Analyzes misrouting patterns and suggests phrases to add to
    EXACT_INTENTS or HEAVY_PHRASES mappings.
    """

    def __init__(self) -> None:
        # Known phrase locations in the codebase
        self._phrase_targets = {
            "greeting": "jarvis/brain_core/prompt_dispatcher.py:EXACT_INTENTS",
            "farewell": "jarvis/brain_core/prompt_dispatcher.py:EXACT_INTENTS",
            "help": "jarvis/brain_core/prompt_dispatcher.py:EXACT_INTENTS",
            "status": "jarvis/brain_core/prompt_dispatcher.py:EXACT_INTENTS",
        }

    def propose(self, pattern: Any) -> dict[str, Any] | None:
        """Generate a phrase proposal from a pattern.

        Args:
            pattern: PatternFinding with misrouting data

        Returns:
            Proposal dict or None if no proposal generated
        """
        if pattern.pattern_type not in ("misrouting", "correction_cluster"):
            return None

        # Extract intent from affected_component
        component = pattern.affected_component
        if ":" in component:
            _, intent = component.split(":", 1)
        else:
            intent = "unknown"

        # Generate proposal to add intent to exact match
        target_file = "jarvis/brain_core/prompt_dispatcher.py"
        target_structure = "EXACT_INTENTS"

        # Extract example phrases from pattern examples
        example_phrases = self._extract_phrases(pattern.examples)

        if not example_phrases:
            return None

        return {
            "target_file": target_file,
            "target_structure": target_structure,
            "proposed_change": {
                "intent": intent,
                "phrases": example_phrases,
            },
            "expected_impact": f"Reduce '{intent}' misrouting by adding {len(example_phrases)} exact-match phrases",
            "rollback_path": f"Remove phrases {example_phrases} from EXACT_INTENTS['{intent}']",
        }

    def _extract_phrases(self, examples: list[str]) -> list[str]:
        """Extract candidate phrases from examples."""
        phrases = []
        for example in examples:
            # Simple extraction - in practice would use NLP
            # Look for quoted phrases or extract key terms
            if "'" in example:
                parts = example.split("'")
                if len(parts) >= 2:
                    phrases.append(parts[1])
            elif '"' in example:
                parts = example.split('"')
                if len(parts) >= 2:
                    phrases.append(parts[1])

        # Deduplicate and limit
        seen = set()
        unique = []
        for p in phrases:
            p_clean = p.strip().lower()
            if p_clean and p_clean not in seen and len(p_clean) >= 2:
                seen.add(p_clean)
                unique.append(p_clean)

        return unique[:5]  # Limit to 5 phrases per proposal

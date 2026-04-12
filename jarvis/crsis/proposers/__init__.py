"""CRSIS proposers package."""

from __future__ import annotations


from jarvis.crsis.proposers.phrases import PhraseProposer
from jarvis.crsis.proposers.thresholds import ThresholdProposer
from jarvis.crsis.proposers.synonyms import SynonymProposer

__all__ = ["PhraseProposer", "ThresholdProposer", "SynonymProposer"]

"""
Jarvis Command Understanding Engine Package.
Independent layer for language-aware parsing, verb lexicon resolution, entity extraction,
simple vs complex command decomposition, and multi-step execution planning.
"""

from .confidence import ConfidenceEvaluator
from .decomposer import CommandDecomposer
from .engine import CommandUnderstandingEngine
from .entity_parser import EntityParser
from .normalizer import CommandNormalizer
from .schema import CommandPlan, ParsedCommand, TargetEntity
from .verb_lexicon import CanonicalVerb, VerbDefinition, VerbLexicon

__all__ = [
    "CommandUnderstandingEngine",
    "CommandPlan",
    "ParsedCommand",
    "TargetEntity",
    "CanonicalVerb",
    "VerbDefinition",
    "VerbLexicon",
    "CommandNormalizer",
    "EntityParser",
    "CommandDecomposer",
    "ConfidenceEvaluator",
]

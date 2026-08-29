"""
Command Understanding Schema for Jarvis.
Defines typed, immutable data structures for parsed single commands and composite execution plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TargetEntity:
    """Represents an extracted target (application, web service, system component)."""
    name: str
    canonical_id: str
    type: Literal["application", "url", "file", "query", "setting", "media", "window", "tab"] = "application"
    confidence: float = 1.0
    executable: str | None = None
    matched_alias: str = ""
    match_method: str = "exact"
    span: tuple[int, int] = (0, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "canonical_id": self.canonical_id,
            "type": self.type,
            "confidence": round(self.confidence, 4),
            "executable": self.executable,
            "matched_alias": self.matched_alias,
            "match_method": self.match_method,
            "span": list(self.span),
        }


@dataclass
class ParsedCommand:
    """A single atomic action parsed from an utterance clause."""
    intent: str
    canonical_verb: str
    target: TargetEntity | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    step: int = 1
    depends_on: list[int] = field(default_factory=list)
    confidence: float = 1.0
    raw_clause: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "canonical_verb": self.canonical_verb,
            "target": self.target.to_dict() if self.target else None,
            "parameters": self.parameters,
            "step": self.step,
            "depends_on": self.depends_on,
            "confidence": round(self.confidence, 4),
            "raw_clause": self.raw_clause,
        }


@dataclass
class CommandPlan:
    """
    Complete execution plan produced by the Command Understanding Engine.
    Distinguishes simple commands, complex multi-step chains, conversations, and unknown inputs.
    """
    type: Literal["simple", "complex", "conversation", "unknown"]
    language: str
    raw_transcript: str
    normalized_transcript: str
    commands: list[ParsedCommand] = field(default_factory=list)
    confidence: float = 1.0
    clarification_needed: bool = False
    clarification_prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "language": self.language,
            "raw_transcript": self.raw_transcript,
            "normalized_transcript": self.normalized_transcript,
            "commands": [c.to_dict() for c in self.commands],
            "confidence": round(self.confidence, 4),
            "clarification_needed": self.clarification_needed,
            "clarification_prompt": self.clarification_prompt,
            "metadata": self.metadata,
        }

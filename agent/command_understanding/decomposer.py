"""
Command Decomposer for Jarvis Command Understanding Engine.
Decomposes complex multi-step utterances into ordered, dependent ParsedCommand steps
while preserving strict execution order.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Tuple

from .entity_parser import EntityParser
from .schema import ParsedCommand
from .verb_lexicon import CanonicalVerb, VerbLexicon

log = logging.getLogger("command_decomposer")


class CommandDecomposer:
    """Decomposes complex spoken utterances into ordered, single-intent action steps."""

    CONJUNCTION_SPLIT_REGEX = (
        r"(?:\s+and\s+then\s+|\s+after\s+that\s+|\s+followed\s+by\s+|\s+và\s+sau\s+đó\s+|\s+rồi\s+sau\s+đó\s+|"
        r"\s+sau\s+đó\s+|\s+tiếp\s+theo\s+|\s+đồng\s+thời\s+|\s+và\s+|\s+and\s+|\s+then\s+|\s+rồi\s+|[,;])"
    )

    def __init__(
        self,
        verb_lexicon: VerbLexicon | None = None,
        entity_parser: EntityParser | None = None
    ):
        self.verb_lexicon = verb_lexicon or VerbLexicon.get_instance()
        self.entity_parser = entity_parser or EntityParser()

    def decompose(self, text: str) -> Tuple[str, list[ParsedCommand]]:
        """
        Decompose an utterance into one or more ordered ParsedCommand objects.
        Returns:
            ("simple" | "complex", list[ParsedCommand])
        """
        cleaned = text.strip()
        if not cleaned:
            return "simple", []

        # 1. Split text along conjunction boundaries
        raw_clauses = [c.strip() for c in re.split(self.CONJUNCTION_SPLIT_REGEX, cleaned, flags=re.IGNORECASE) if c.strip()]

        # Filter out trivial fragments that contain no verb or target
        valid_clauses: list[str] = []
        for c in raw_clauses:
            if len(c.split()) >= 1 and not (len(c.split()) == 1 and c.lower() in ("và", "and", "then", "rồi")):
                valid_clauses.append(c)

        if not valid_clauses:
            valid_clauses = [cleaned]

        # 2. Parse each clause into a ParsedCommand
        commands: list[ParsedCommand] = []
        for i, clause in enumerate(valid_clauses, start=1):
            verb_res = self.verb_lexicon.find_verb(clause)
            if verb_res:
                canonical_verb, matched_surface, intent, verb_conf = verb_res
            else:
                canonical_verb = "UNKNOWN"
                intent = "UNKNOWN"
                verb_conf = 0.50

            target_entity, params = self.entity_parser.parse_target_and_params(
                clause=clause,
                canonical_verb=canonical_verb,
                intent=intent
            )

            # Adjust intent if target implies specific action (e.g. YouTube URL -> OPEN_APPLICATION)
            if intent == "UNKNOWN" and target_entity:
                intent = "OPEN_APPLICATION"
                canonical_verb = CanonicalVerb.OPEN
                verb_conf = 0.85

            depends_on = [i - 1] if i > 1 else []
            confidence = round((verb_conf + (target_entity.confidence if target_entity else 0.85)) / 2.0, 4)

            cmd = ParsedCommand(
                intent=intent,
                canonical_verb=canonical_verb,
                target=target_entity,
                parameters=params,
                step=i,
                depends_on=depends_on,
                confidence=confidence,
                raw_clause=clause,
            )
            commands.append(cmd)

        plan_type = "complex" if len(commands) > 1 else "simple"
        return plan_type, commands

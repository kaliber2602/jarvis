"""
Confidence Scoring & Threshold Evaluation for Jarvis Command Understanding Engine.
Evaluates overall plan confidence and flags ambiguous commands requiring clarification.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .schema import ParsedCommand

log = logging.getLogger("confidence_evaluator")


class ConfidenceEvaluator:
    """Evaluates confidence levels and determines execution safety for parsed commands."""

    HIGH_THRESHOLD: float = 0.85
    MEDIUM_THRESHOLD: float = 0.60

    @classmethod
    def evaluate(cls, commands: list[ParsedCommand], raw_text: str) -> Tuple[float, bool, str | None]:
        """
        Calculate aggregate plan confidence and determine if clarification is required.
        Returns:
            (overall_confidence, clarification_needed, clarification_prompt)
        """
        if not commands:
            return 0.0, False, None

        confidences = [c.confidence for c in commands]
        avg_conf = sum(confidences) / len(confidences)

        # Check if any step is ambiguous
        for cmd in commands:
            if cmd.intent == "UNKNOWN" or (cmd.target and cmd.target.confidence < cls.MEDIUM_THRESHOLD):
                target_name = cmd.target.name if cmd.target else "that application"
                prompt = f"Did you mean to {cmd.canonical_verb.lower()} {target_name}?"
                return round(avg_conf * 0.7, 4), True, prompt

        if avg_conf < cls.MEDIUM_THRESHOLD:
            return round(avg_conf, 4), True, f"I am not sure I understood '{raw_text}'. Could you please rephrase?"

        return round(avg_conf, 4), False, None

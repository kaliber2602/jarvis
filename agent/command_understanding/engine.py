"""
Central Command Understanding Engine for Jarvis.
Orchestrates the entire understanding pipeline:
Raw ASR Transcript -> Normalization -> Verb Lexicon -> Entity Extraction -> Decomposition -> Confidence -> CommandPlan.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from agent.language.detector import LanguageDetector
from agent.llm.qwen_provider import QwenProvider
from agent.voice_memory import VoiceMemory
from .confidence import ConfidenceEvaluator
from .decomposer import CommandDecomposer
from .entity_parser import EntityParser
from .normalizer import CommandNormalizer
from .schema import CommandPlan, ParsedCommand, TargetEntity
from .verb_lexicon import CanonicalVerb, VerbLexicon

log = logging.getLogger("command_understanding")


class CommandUnderstandingEngine:
    """
    Independent Command Understanding Engine.
    Processes raw ASR transcripts into validated, structured execution plans.
    """

    _instance: CommandUnderstandingEngine | None = None

    CONVERSATION_INDICATORS = (
        "what is", "what are", "who is", "who are", "how is", "how do", "why is",
        "why do", "can you tell me", "tell me about", "explain", "help me understand",
        "thời tiết", "là gì", "thế nào", "tại sao", "giải thích", "ai là", "hôm nay thế nào",
        "chào jarvis", "hello jarvis", "hi jarvis", "good morning", "good evening", "how are you"
    )

    @classmethod
    def get_instance(cls) -> CommandUnderstandingEngine:
        if cls._instance is None:
            cls._instance = CommandUnderstandingEngine()
        return cls._instance

    def __init__(self):
        self.verb_lexicon = VerbLexicon.get_instance()
        self.entity_parser = EntityParser()
        self.decomposer = CommandDecomposer(self.verb_lexicon, self.entity_parser)
        self.language_detector = LanguageDetector.get_instance()
        self.llm_provider = QwenProvider.get_instance()

    def parse(self, raw_transcript: str, context: dict[str, Any] | None = None) -> CommandPlan:
        """
        Main entry point: Parse raw ASR speech transcript into a validated CommandPlan.
        """
        raw = (raw_transcript or "").strip()
        if not raw:
            return CommandPlan(
                type="unknown",
                language="en",
                raw_transcript="",
                normalized_transcript="",
                confidence=0.0,
            )

        # 1. Clean & Strip Dangling Trailing Verbs
        cleaned = CommandNormalizer.clean_text(raw)
        cleaned = CommandNormalizer.strip_dangling_verbs(cleaned)
        log.info("[COMMAND_NORMALIZER] Raw: '%s' -> Cleaned: '%s'", raw, cleaned)

        # 2. Check for ambient filler noise
        if CommandNormalizer.is_filler_noise(cleaned):
            log.info("[COMMAND_CLASSIFIER] Filtered out filler noise: '%s'", cleaned)
            return CommandPlan(
                type="unknown",
                language="en",
                raw_transcript=raw,
                normalized_transcript=cleaned,
                confidence=0.0,
            )

        # 3. Detect Language
        lang_type, lang_conf, _ = self.language_detector.detect(cleaned)
        lang_code = "vi" if lang_type.value == "vi" else "en"

        # 4. Check VoiceMemory learned phonetic overrides & transliterate phonetics
        vm_text, _ = VoiceMemory.get_instance().normalize(cleaned)
        transliterated = CommandNormalizer.transliterate_phonetics(vm_text)

        # 5. Check if utterance is conversational / QA
        low_clean = cleaned.lower()
        is_conversational_question = any(q in low_clean for q in self.CONVERSATION_INDICATORS)
        has_any_verb = bool(self.verb_lexicon.find_verb(transliterated) or self.verb_lexicon.find_verb(cleaned))

        if is_conversational_question and not has_any_verb:
            log.info("[COMMAND_CLASSIFIER] Classified as CONVERSATION: '%s'", cleaned)
            return CommandPlan(
                type="conversation",
                language=lang_code,
                raw_transcript=raw,
                normalized_transcript=transliterated,
                confidence=0.92,
            )

        # 6. Decompose into Ordered Parsed Commands
        plan_type, commands = self.decomposer.decompose(transliterated)
        if not commands and cleaned != transliterated:
            plan_type, commands = self.decomposer.decompose(cleaned)

        # Log breakdown
        for cmd in commands:
            log.info(
                "[VERB_LEXICON] Step %d: '%s' -> Verb: %s | Intent: %s (conf=%.2f)",
                cmd.step, cmd.raw_clause, cmd.canonical_verb, cmd.intent, cmd.confidence
            )
            if cmd.target:
                log.info(
                    "[ENTITY_PARSER] Step %d Target: '%s' (type=%s, conf=%.2f)",
                    cmd.step, cmd.target.name, cmd.target.type, cmd.target.confidence
                )

        # 7. Evaluate Confidence & Clarification Thresholds
        conf, clar_needed, clar_prompt = ConfidenceEvaluator.evaluate(commands, cleaned)

        # If all steps have UNKNOWN intent and low confidence, treat as conversation or unknown
        if all(c.intent == "UNKNOWN" for c in commands) and conf < 0.65:
            final_type = "conversation" if len(cleaned.split()) >= 3 else "unknown"
            return CommandPlan(
                type=final_type,
                language=lang_code,
                raw_transcript=raw,
                normalized_transcript=transliterated,
                confidence=conf,
                clarification_needed=clar_needed,
                clarification_prompt=clar_prompt,
            )

        # 8. Construct Normalized Transcript
        # Replace matched aliases with canonical application names for clear reporting
        normalized_str = transliterated
        for cmd in commands:
            if cmd.target and cmd.target.matched_alias and cmd.target.matched_alias in normalized_str.lower():
                pattern = re.compile(re.escape(cmd.target.matched_alias), re.IGNORECASE)
                normalized_str = pattern.sub(cmd.target.name, normalized_str, count=1)

        log.info(
            "[COMMAND_PLANNER] Built %s Plan with %d steps (Overall Conf=%.2f): %s",
            plan_type.upper(), len(commands), conf, [f"{c.canonical_verb}:{c.target.name if c.target else 'None'}" for c in commands]
        )

        return CommandPlan(
            type=plan_type,  # "simple" | "complex"
            language=lang_code,
            raw_transcript=raw,
            normalized_transcript=normalized_str,
            commands=commands,
            confidence=conf,
            clarification_needed=clar_needed,
            clarification_prompt=clar_prompt,
            metadata={
                "steps_count": len(commands),
                "has_dependencies": any(bool(c.depends_on) for c in commands),
            }
        )

"""
Multi-Tier Transcript Normalization Architecture for Jarvis:
1. RuleBasedNormalizer: Whitespace, diacritic handling, noise filtering, regex expansions.
2. DictionaryNormalizer: Technical vocabulary, application aliases, phonetic transliterations, VoiceMemory.
3. LLMNormalizer: Lightweight Small LLM correction fallback for low-confidence utterances.
4. HybridNormalizer: Coordinates all tiers with fast-exit on high confidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import os
import re
from typing import Any, Tuple

from .app_registry import AppRegistry
from .phonetics import (
    calculate_entity_similarity,
    remove_vietnamese_diacritics,
    transliterate_vietnamese_phonetics,
)
from .voice_memory import VoiceMemory

log = logging.getLogger("normalizer_layers")


@dataclass
class NormalizationResult:
    raw_transcript: str
    normalized_transcript: str
    confidence: float
    corrected_by: str  # "rule" | "dictionary" | "llm" | "passthrough"
    is_modified: bool = False


class BaseNormalizer(ABC):
    """Abstract Base Class for Normalizer Tiers."""

    @abstractmethod
    def normalize(self, text: str) -> NormalizationResult:
        pass


class RuleBasedNormalizer(BaseNormalizer):
    """Tier 1: Applies deterministic text cleaning, whitespace normalization, and phonetics."""

    FILLER_NOISE_WORDS = {
        "ah", "oh", "um", "uh", "eh", "er", "hm", "hmm", "mm", "the", "a",
        "so", "yeah", "no", "oh up", "what a man", "right yeah no", "you know i know",
        "yeah this", "oh yeah", "now", "up", "ạ", "ờ", "ừ", "hả", "nè"
    }

    def normalize(self, text: str) -> NormalizationResult:
        raw = text.strip()
        if not raw:
            return NormalizationResult(raw_transcript="", normalized_transcript="", confidence=1.0, corrected_by="rule")

        # 1. Clean extra spaces
        cleaned = re.sub(r"\s+", " ", raw).strip()

        # 2. Transliterate known Vietnamese phonetic approximations
        transliterated = transliterate_vietnamese_phonetics(cleaned)
        is_mod = (transliterated != raw)

        return NormalizationResult(
            raw_transcript=raw,
            normalized_transcript=transliterated,
            confidence=0.88 if is_mod else 0.75,
            corrected_by="rule",
            is_modified=is_mod,
        )


class DictionaryNormalizer(BaseNormalizer):
    """Tier 2: Applies VoiceMemory learned corrections and AppRegistry curated aliases."""

    def __init__(self):
        self.voice_memory = VoiceMemory.get_instance()
        self.app_registry = AppRegistry.get_instance()

    def normalize(self, text: str) -> NormalizationResult:
        raw = text.strip()
        if not raw:
            return NormalizationResult(raw_transcript="", normalized_transcript="", confidence=1.0, corrected_by="dictionary")

        # 1. Check VoiceMemory learned overrides
        vm_text, was_vm_corrected = self.voice_memory.normalize(raw)
        if was_vm_corrected:
            log.info("[NORMALIZER] VoiceMemory matched: '%s' -> '%s'", raw, vm_text)
            return NormalizationResult(
                raw_transcript=raw,
                normalized_transcript=vm_text,
                confidence=0.98,
                corrected_by="dictionary",
                is_modified=True,
            )

        # 2. Check AppRegistry alias expansions
        cleaned_lower = vm_text.lower()
        matched_app = self.app_registry.find_by_exact_alias(cleaned_lower)
        if matched_app:
            return NormalizationResult(
                raw_transcript=raw,
                normalized_transcript=matched_app.display_name,
                confidence=0.96,
                corrected_by="dictionary",
                is_modified=True,
            )

        return NormalizationResult(
            raw_transcript=raw,
            normalized_transcript=vm_text,
            confidence=0.70,
            corrected_by="dictionary",
            is_modified=was_vm_corrected,
        )


class LLMNormalizer(BaseNormalizer):
    """Tier 3: Small LLM transcript correction fallback for noisy or highly corrupted STT."""

    def __init__(self):
        self.enabled = os.environ.get("NORMALIZER_LLM_ENABLED", "True").strip().lower() in ("true", "1", "yes")
        self.api_url = os.environ.get("SMALL_LLM_API_URL", os.environ.get("LLM_API_URL", "")).strip()
        self.api_key = os.environ.get("SMALL_LLM_API_KEY", os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))).strip()
        self.model = os.environ.get("SMALL_LLM_MODEL", "qwen2.5:1.5b").strip()

    def normalize(self, text: str) -> NormalizationResult:
        raw = text.strip()
        if not raw or not self.enabled:
            return NormalizationResult(raw_transcript=raw, normalized_transcript=raw, confidence=0.5, corrected_by="passthrough")

        # If external API is configured, invoke lightweight correction
        if self.api_url and self.api_key:
            try:
                import httpx
                prompt = (
                    "You are a voice assistant transcript normalizer. "
                    "The user spoke a voice command (English or Vietnamese) that might have speech recognition typos or misheard pronunciation.\n"
                    "Normalize application names, command keywords, and formatting without changing the user's intent.\n"
                    "Output ONLY the corrected command sentence and nothing else.\n\n"
                    f"Spoken: {raw}\n"
                    "Corrected:"
                )
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 60,
                }
                resp = httpx.post(f"{self.api_url}/chat/completions", headers=headers, json=payload, timeout=2.5)
                if resp.status_code == 200:
                    data = resp.json()
                    corrected = data["choices"][0]["message"]["content"].strip().strip('"').strip("'")
                    if corrected and len(corrected) < len(raw) * 2:
                        log.info("[NORMALIZER] Small LLM corrected: '%s' -> '%s'", raw, corrected)
                        return NormalizationResult(
                            raw_transcript=raw,
                            normalized_transcript=corrected,
                            confidence=0.92,
                            corrected_by="llm",
                            is_modified=True,
                        )
            except Exception as e:
                log.debug("[NORMALIZER] LLM normalization fallback skipped: %s", e)

        return NormalizationResult(raw_transcript=raw, normalized_transcript=raw, confidence=0.70, corrected_by="passthrough")


class HybridNormalizer(BaseNormalizer):
    """
    Coordinator Normalizer:
    Executes Rule & Dictionary normalizers first. If confidence is >= threshold, returns immediately.
    Only falls back to Small LLM when confidence is low.
    """

    def __init__(self, confidence_threshold: float = 0.82):
        self.confidence_threshold = float(os.environ.get("NORMALIZER_CONFIDENCE_THRESHOLD", str(confidence_threshold)))
        self.rule_normalizer = RuleBasedNormalizer()
        self.dict_normalizer = DictionaryNormalizer()
        self.llm_normalizer = LLMNormalizer()

    def normalize(self, text: str) -> NormalizationResult:
        raw = text.strip()
        if not raw:
            return NormalizationResult(raw_transcript="", normalized_transcript="", confidence=1.0, corrected_by="rule")

        # 1. Rule-based pass
        rule_res = self.rule_normalizer.normalize(raw)

        # 2. Dictionary / VoiceMemory pass
        dict_res = self.dict_normalizer.normalize(rule_res.normalized_transcript)

        combined_text = dict_res.normalized_transcript
        best_conf = max(rule_res.confidence, dict_res.confidence)
        best_source = "dictionary" if dict_res.is_modified else ("rule" if rule_res.is_modified else "passthrough")

        # 3. If confident, return immediately
        if best_conf >= self.confidence_threshold:
            return NormalizationResult(
                raw_transcript=raw,
                normalized_transcript=combined_text,
                confidence=best_conf,
                corrected_by=best_source,
                is_modified=(combined_text != raw),
            )

        # 4. Low confidence -> Invoke Small LLM Normalizer
        log.debug("[NORMALIZER] Low confidence (%.2f < %.2f) for '%s' -> Invoking Small LLM fallback", best_conf, self.confidence_threshold, raw)
        llm_res = self.llm_normalizer.normalize(combined_text)
        if llm_res.is_modified and llm_res.confidence > best_conf:
            return NormalizationResult(
                raw_transcript=raw,
                normalized_transcript=llm_res.normalized_transcript,
                confidence=llm_res.confidence,
                corrected_by="llm",
                is_modified=True,
            )

        return NormalizationResult(
            raw_transcript=raw,
            normalized_transcript=combined_text,
            confidence=best_conf,
            corrected_by=best_source,
            is_modified=(combined_text != raw),
        )

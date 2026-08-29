"""
Language-aware Transcript Normalizer for Jarvis Command Understanding Engine.
Cleans raw ASR transcript, removes trailing speech artifacts, transliterates phonetics,
and preserves the original raw transcript for debugging and auditability.
"""

from __future__ import annotations

import logging
import re
from typing import Set

from agent.phonetics import (
    remove_vietnamese_diacritics,
    transliterate_vietnamese_phonetics,
)

log = logging.getLogger("command_normalizer")


class CommandNormalizer:
    """Text normalization utilities for the Command Understanding Engine."""

    FILLER_NOISE_WORDS: Set[str] = {
        "ah", "oh", "um", "uh", "eh", "er", "hm", "hmm", "mm", "the", "a",
        "so", "yeah", "no", "oh up", "what a man", "right yeah no", "you know i know",
        "yeah this", "oh yeah", "now", "up", "ạ", "ờ", "ừ", "hả", "nè", "ha", "nha"
    }

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Remove excess whitespace and abnormal characters."""
        if not text:
            return ""
        t = re.sub(r"\s+", " ", text).strip()
        return t

    @classmethod
    def strip_dangling_verbs(cls, text: str) -> str:
        """
        Strip incomplete trailing verbs, conjunctions, or prepositions left over
        when the speaker is cut off mid-sentence or ASR has residual noise.
        e.g. 'Mở YouTube, mở Google Chrome, mở' -> 'Mở YouTube, mở Google Chrome'
        e.g. 'Open VS Code and' -> 'Open VS Code'
        """
        if not text:
            return ""
        t = text.strip()
        dangling_pattern = r"(?:[\s,;.!?]+(?:mở|open|bật|đóng|close|tắt|chạy|run|search|tìm|và|and|then|rồi|sau đó|nhưng|hoặc|or|for|to|with|tạo|create))+$"
        t_cleaned = re.sub(dangling_pattern, "", t, flags=re.IGNORECASE).strip()
        return t_cleaned if t_cleaned else t

    @classmethod
    def transliterate_phonetics(cls, text: str) -> str:
        """Transliterate phonetic Vietnamese approximations to English software names."""
        return transliterate_vietnamese_phonetics(text)

    @classmethod
    def is_filler_noise(cls, text: str) -> bool:
        """Check if transcript consists solely of filler noise."""
        cleaned = text.strip().lower()
        if not cleaned or len(cleaned) < 2:
            return True
        return cleaned in cls.FILLER_NOISE_WORDS

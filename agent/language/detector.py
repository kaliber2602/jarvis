"""
Language Detection Engine for Jarvis:
Combines fastText (if available), Vietnamese Diacritic Regex Analysis,
and Bilingual Dictionaries to detect Vietnamese, English, and Mixed EN+VI speech.

Invariant: Input may be EN / VI / Mixed, but Jarvis AI responses are ALWAYS ENGLISH.
"""

from __future__ import annotations

from enum import Enum
import logging
import os
import re
from typing import Any, Tuple

log = logging.getLogger("language_detector")


class LanguageType(str, Enum):
    VIETNAMESE = "vi"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class LanguageDetector:
    """
    Multi-Signal Language Detector for spoken user commands.
    Distinguishes English, Vietnamese, and code-switching Mixed speech.
    """

    _instance: LanguageDetector | None = None

    VI_DIACRITICS_PATTERN = re.compile(
        r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]"
        r"|[ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]",
        re.IGNORECASE,
    )

    COMMON_VI_WORDS = {
        "mở", "bật", "chạy", "đóng", "tắt", "tìm", "kiếm", "cho", "tôi", "và",
        "rồi", "sau", "đó", "hôm", "nay", "qua", "gì", "là", "ai", "đi", "ngủ",
        "cửa", "sổ", "trang", "bài", "nhạc", "xem", "chuyển", "sang", "chọn",
        "thứ", "nhất", "hai", "ba", "bốn", "năm", "đầu", "tiên", "cuối", "cùng",
        "để", "tôi", "làm", "việc", "nhé", "ạ", "ơi", "giúp", "với", "không",
    }

    COMMON_EN_WORDS = {
        "open", "close", "launch", "start", "run", "search", "find", "for", "me",
        "and", "then", "after", "that", "today", "yesterday", "what", "is", "who",
        "go", "to", "sleep", "window", "tab", "song", "music", "play", "pause",
        "switch", "select", "first", "second", "third", "last", "the", "a", "an",
        "in", "on", "at", "because", "need", "debug", "code", "file", "folder",
    }

    @classmethod
    def get_instance(cls) -> LanguageDetector:
        if cls._instance is None:
            cls._instance = LanguageDetector()
        return cls._instance

    def __init__(self):
        self._fasttext_model = None
        self._load_fasttext()

    def _load_fasttext(self) -> None:
        """Attempt to load fasttext model if configured or available."""
        model_path = os.environ.get("FASTTEXT_MODEL_PATH", "")
        if model_path and os.path.isfile(model_path):
            try:
                import fasttext
                self._fasttext_model = fasttext.load_model(model_path)
                log.info("[LANGUAGE] fastText model loaded from %s", model_path)
            except Exception as e:
                log.debug("[LANGUAGE] fastText load failed: %s", e)

    def detect(self, text: str) -> Tuple[LanguageType, float, dict[str, Any]]:
        """
        Detect language of user input.
        Returns:
            (LanguageType, confidence, metadata_details)
        """
        raw = text.strip()
        if not raw:
            return LanguageType.UNKNOWN, 0.0, {}

        # 1. FastText inference if model exists
        if self._fasttext_model is not None:
            try:
                labels, probs = self._fasttext_model.predict(raw, k=2)
                top_label = labels[0].replace("__label__", "")
                top_prob = float(probs[0])
                if top_label in ("vi", "vie"):
                    return LanguageType.VIETNAMESE, top_prob, {"fasttext_label": top_label}
                elif top_label in ("en", "eng"):
                    return LanguageType.ENGLISH, top_prob, {"fasttext_label": top_label}
            except Exception as e:
                log.debug("[LANGUAGE] fastText inference error: %s", e)

        # 2. Heuristic Diacritics and Vocabulary Frequency Analysis
        words = re.findall(r"\w+", raw.lower())
        total_words = len(words)
        if total_words == 0:
            return LanguageType.UNKNOWN, 0.0, {}

        has_vi_diacritics = bool(self.VI_DIACRITICS_PATTERN.search(raw))
        vi_count = sum(1 for w in words if w in self.COMMON_VI_WORDS)
        en_count = sum(1 for w in words if w in self.COMMON_EN_WORDS)

        # Diacritics presence
        diacritic_words = sum(1 for w in words if self.VI_DIACRITICS_PATTERN.search(w))

        # Decision Logic
        if (diacritic_words > 0 or vi_count > 0) and en_count > 0:
            # Both languages present in the sentence
            log.info("[LANGUAGE] Detected MIXED Vietnamese + English utterance: '%s'", raw)
            return LanguageType.MIXED, 0.92, {
                "vi_words": vi_count,
                "en_words": en_count,
                "diacritic_words": diacritic_words,
            }

        if diacritic_words > 0 or vi_count > en_count:
            conf = min(0.98, 0.70 + 0.1 * diacritic_words + 0.05 * vi_count)
            log.info("[LANGUAGE] Detected VIETNAMESE utterance: '%s' (conf=%.2f)", raw, conf)
            return LanguageType.VIETNAMESE, conf, {
                "vi_words": vi_count,
                "diacritic_words": diacritic_words,
            }

        conf = min(0.98, 0.75 + 0.05 * en_count)
        log.info("[LANGUAGE] Detected ENGLISH utterance: '%s' (conf=%.2f)", raw, conf)
        return LanguageType.ENGLISH, conf, {"en_words": en_count}

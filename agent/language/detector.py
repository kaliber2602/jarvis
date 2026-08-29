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

    TECH_AND_LOANWORDS = {
        "neural network", "neural networks", "machine learning", "deep learning",
        "docker", "docker desktop", "docker compose", "fastapi", "python", "javascript",
        "typescript", "visual studio code", "vs code", "vscode", "chrome", "google chrome",
        "google", "youtube", "spotify", "notepad", "discord", "antigravity", "cursor",
        "github", "gitlab", "terminal", "powershell", "cmd", "postman", "figma", "steam",
        "yesterday", "tutorial", "information", "course", "install", "how to install",
        "debug", "api", "rest api", "graphql", "dataset", "framework", "database",
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

    def analyze_code_switching(self, text: str) -> dict[str, Any]:
        """
        Analyze code-switching structure, token/segment language tagging, and technical loanwords
        WITHOUT mutating or translating the raw transcript text.
        """
        raw = text.strip()
        if not raw:
            return {
                "text": "",
                "primary_language": "en",
                "languages": ["en"],
                "mixed_language": False,
                "segments": [],
                "entities": [],
            }

        low = raw.lower()
        words = re.findall(r"\w+", low)
        detected_entities = [e for e in self.TECH_AND_LOANWORDS if e in low]

        # Segment / Token language tagging
        segments = []
        vi_count = 0
        en_count = 0

        for w in words:
            if self.VI_DIACRITICS_PATTERN.search(w) or w in self.COMMON_VI_WORDS:
                segments.append({"text": w, "language": "vi"})
                vi_count += 1
            elif w in self.COMMON_EN_WORDS or any(w in ent.split() for ent in self.TECH_AND_LOANWORDS):
                segments.append({"text": w, "language": "en"})
                en_count += 1
            else:
                # Neutral / proper noun token
                segments.append({"text": w, "language": "neutral"})

        is_mixed = (vi_count > 0 and en_count > 0) or (vi_count > 0 and bool(detected_entities)) or (en_count > 0 and bool(self.VI_DIACRITICS_PATTERN.search(raw)))
        primary = "vi" if vi_count >= en_count and (vi_count > 0 or self.VI_DIACRITICS_PATTERN.search(raw)) else "en"
        languages = ["vi", "en"] if is_mixed else [primary]

        return {
            "text": raw,
            "primary_language": primary,
            "languages": languages,
            "mixed_language": is_mixed,
            "segments": segments,
            "entities": detected_entities,
        }

    def detect(self, text: str) -> Tuple[LanguageType, float, dict[str, Any]]:
        """
        Detect language of user input.
        Returns:
            (LanguageType, confidence, metadata_details)
        """
        raw = text.strip()
        if not raw:
            return LanguageType.UNKNOWN, 0.0, {}

        # 1. Detailed Code-Switching & Linguistic Analysis
        analysis = self.analyze_code_switching(raw)

        if analysis["mixed_language"]:
            log.info("[LANGUAGE] Detected MIXED Vietnamese + English utterance: '%s' (entities=%s)", raw, analysis["entities"])
            return LanguageType.MIXED, 0.95, analysis

        if analysis["primary_language"] == "vi":
            diacritic_count = len(self.VI_DIACRITICS_PATTERN.findall(raw))
            conf = min(0.98, 0.75 + 0.05 * diacritic_count)
            log.info("[LANGUAGE] Detected VIETNAMESE utterance: '%s' (conf=%.2f)", raw, conf)
            return LanguageType.VIETNAMESE, conf, analysis

        conf = 0.90 if any(w in raw.lower().split() for w in self.COMMON_EN_WORDS) else 0.80
        log.info("[LANGUAGE] Detected ENGLISH utterance: '%s' (conf=%.2f)", raw, conf)
        return LanguageType.ENGLISH, conf, analysis

from __future__ import annotations

import sys
from pathlib import Path
import unittest

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.language.detector import LanguageDetector, LanguageType
from agent.normalizer import VoiceNormalizationPipeline
from agent.command_understanding.engine import CommandUnderstandingEngine


class TestCodeSwitchingIntegration(unittest.TestCase):
    """
    Test suite for Vietnamese, English, Code-Switching (VI+EN / EN+VI),
    and Technical Term preservation across language and command layers.
    """

    def setUp(self):
        self.detector = LanguageDetector.get_instance()
        self.pipeline = VoiceNormalizationPipeline.get_instance()
        self.understanding = CommandUnderstandingEngine.get_instance()

    def test_pure_vietnamese_commands(self):
        vi_phrases = [
            "Mở Chrome",
            "Mở cho tôi Notepad",
            "Tìm khóa học Python",
            "Cho tôi biết thời tiết hôm nay",
        ]
        for phrase in vi_phrases:
            lang_type, conf, meta = self.detector.detect(phrase)
            self.assertIn(lang_type, (LanguageType.VIETNAMESE, LanguageType.MIXED))
            self.assertIn("vi", meta["languages"])

            ctx = self.pipeline.process_transcript(phrase)
            self.assertTrue(len(ctx.raw_transcript) > 0)

    def test_pure_english_commands(self):
        en_phrases = [
            "Open Chrome",
            "Open Notepad",
            "Find a Python course",
            "Tell me the weather",
        ]
        for phrase in en_phrases:
            lang_type, conf, meta = self.detector.detect(phrase)
            self.assertEqual(lang_type, LanguageType.ENGLISH)
            self.assertEqual(meta["primary_language"], "en")

    def test_vietnamese_english_code_switching(self):
        mixed_vi_en = [
            "Mở cho tôi khóa học neural network",
            "Mở cho tôi khóa học machine learning",
            "Tìm giúp tôi tutorial về Docker",
            "Tìm giúp tôi tutorial về FastAPI",
            "Mở Visual Studio Code",
            "Cho tôi information về FastAPI",
            "Play bài Yesterday",
        ]
        for phrase in mixed_vi_en:
            lang_type, conf, meta = self.detector.detect(phrase)
            # Must detect code-switching
            self.assertTrue(meta["mixed_language"], f"Failed mixed detection for '{phrase}'")
            self.assertIn("vi", meta["languages"])
            self.assertIn("en", meta["languages"])

            # RAW transcript must NOT be mutated or translated
            ctx = self.pipeline.process_transcript(phrase)
            self.assertEqual(ctx.raw_transcript, phrase)

    def test_english_vietnamese_code_switching(self):
        mixed_en_vi = [
            "Open giúp tôi Chrome",
            "Find cho tôi một khóa học Python",
            "Play cho tôi bài Yesterday",
            "Tell me về Docker",
            "Search giúp tôi neural network course",
        ]
        for phrase in mixed_en_vi:
            lang_type, conf, meta = self.detector.detect(phrase)
            self.assertTrue(meta["mixed_language"], f"Failed mixed detection for '{phrase}'")
            self.assertIn("vi", meta["languages"])
            self.assertIn("en", meta["languages"])

    def test_technical_terms_preservation(self):
        # Verification that technical terms are NOT translated into Vietnamese in raw transcript
        tech_phrases = [
            ("Mở cho tôi khóa học neural network", "neural network"),
            ("Mở Docker Desktop", "Docker Desktop"),
            ("Chạy Docker Compose", "Docker Compose"),
            ("Tìm tutorial FastAPI", "FastAPI"),
            ("Mở Visual Studio Code", "Visual Studio Code"),
            ("Mở Spotify", "Spotify"),
        ]
        for phrase, term in tech_phrases:
            ctx = self.pipeline.process_transcript(phrase)
            self.assertIn(term.lower(), ctx.raw_transcript.lower())
            # Ensure not translated to Vietnamese (e.g. 'mạng nơ-ron')
            self.assertNotIn("mạng nơ-ron", ctx.raw_transcript.lower())


if __name__ == "__main__":
    unittest.main()

"""
Comprehensive Unit & Integration Test Suite for Jarvis Command Understanding Engine.
Verifies:
1. Simple English Commands
2. Simple Vietnamese Commands
3. Synonym Convergence (EN & VI)
4. Complex English Commands
5. Complex Vietnamese Commands
6. Mixed-Language (Code-Switching) Commands
7. Entity & Parameter Extraction
8. Whisper Phonetic / Typo Normalization
9. Command vs Conversation Classification
10. Execution Order & Dependency Preservation
"""

import sys
import unittest

sys.path.insert(0, ".")

from agent.command_understanding import (
    CanonicalVerb,
    CommandPlan,
    CommandUnderstandingEngine,
    ParsedCommand,
    VerbLexicon,
)


class TestCommandUnderstandingEngine(unittest.TestCase):
    """Test suite verifying all capabilities of the Command Understanding Engine."""

    @classmethod
    def setUpClass(cls):
        cls.engine = CommandUnderstandingEngine.get_instance()

    # 1. Simple English Commands
    def test_simple_english_commands(self):
        cases = [
            ("Open Chrome", "OPEN_APPLICATION", CanonicalVerb.OPEN, "Google Chrome"),
            ("Close Spotify", "CLOSE_APPLICATION", CanonicalVerb.CLOSE, "Spotify"),
            ("Launch VS Code", "OPEN_APPLICATION", CanonicalVerb.OPEN, "Visual Studio Code"),
            ("Play music", "MEDIA_CONTROL", CanonicalVerb.PLAY, None),
            ("Pause the music", "MEDIA_CONTROL", CanonicalVerb.PAUSE, None),
            ("Search YouTube", "SEARCH_WEB", CanonicalVerb.SEARCH, "YouTube"),
        ]
        for utterance, expected_intent, expected_verb, expected_target in cases:
            with self.subTest(utterance=utterance):
                plan = self.engine.parse(utterance)
                self.assertEqual(plan.type, "simple")
                self.assertGreaterEqual(len(plan.commands), 1)
                cmd = plan.commands[0]
                self.assertEqual(cmd.intent, expected_intent)
                self.assertEqual(cmd.canonical_verb, expected_verb)
                if expected_target:
                    self.assertIsNotNone(cmd.target)
                    self.assertEqual(cmd.target.name, expected_target)

    # 2. Simple Vietnamese Commands
    def test_simple_vietnamese_commands(self):
        cases = [
            ("Mở Chrome", "OPEN_APPLICATION", CanonicalVerb.OPEN, "Google Chrome"),
            ("Đóng Spotify", "CLOSE_APPLICATION", CanonicalVerb.CLOSE, "Spotify"),
            ("Khởi chạy VS Code", "OPEN_APPLICATION", CanonicalVerb.OPEN, "Visual Studio Code"),
            ("Phát nhạc", "MEDIA_CONTROL", CanonicalVerb.PLAY, None),
            ("Tạm dừng nhạc", "MEDIA_CONTROL", CanonicalVerb.PAUSE, None),
            ("Tìm kiếm YouTube", "SEARCH_WEB", CanonicalVerb.SEARCH, "YouTube"),
        ]
        for utterance, expected_intent, expected_verb, expected_target in cases:
            with self.subTest(utterance=utterance):
                plan = self.engine.parse(utterance)
                self.assertEqual(plan.type, "simple")
                self.assertGreaterEqual(len(plan.commands), 1)
                cmd = plan.commands[0]
                self.assertEqual(cmd.intent, expected_intent)
                self.assertEqual(cmd.canonical_verb, expected_verb)
                if expected_target:
                    self.assertIsNotNone(cmd.target)
                    self.assertEqual(cmd.target.name, expected_target)

    # 3. Synonym Convergence (All map to same canonical verb and intent)
    def test_synonym_convergence(self):
        synonyms = [
            "open chrome",
            "launch chrome",
            "start chrome",
            "run chrome",
            "mở chrome",
            "khởi chạy chrome",
            "bật chrome",
        ]
        for syn in synonyms:
            with self.subTest(syn=syn):
                plan = self.engine.parse(syn)
                self.assertEqual(plan.type, "simple")
                cmd = plan.commands[0]
                self.assertEqual(cmd.canonical_verb, CanonicalVerb.OPEN)
                self.assertEqual(cmd.intent, "OPEN_APPLICATION")
                self.assertEqual(cmd.target.name, "Google Chrome")

    # 4. Complex English Commands
    def test_complex_english_commands(self):
        plan1 = self.engine.parse("Open Chrome and search YouTube")
        self.assertEqual(plan1.type, "complex")
        self.assertEqual(len(plan1.commands), 2)
        self.assertEqual(plan1.commands[0].canonical_verb, CanonicalVerb.OPEN)
        self.assertEqual(plan1.commands[1].canonical_verb, CanonicalVerb.SEARCH)

        plan2 = self.engine.parse("Launch VS Code, create a Python file, and type hello world")
        self.assertEqual(plan2.type, "complex")
        self.assertEqual(len(plan2.commands), 3)
        self.assertEqual(plan2.commands[0].canonical_verb, CanonicalVerb.OPEN)
        self.assertEqual(plan2.commands[1].canonical_verb, CanonicalVerb.CREATE)
        self.assertEqual(plan2.commands[2].canonical_verb, CanonicalVerb.TYPE)
        self.assertEqual(plan2.commands[2].parameters.get("text"), "hello world")

    # 5. Complex Vietnamese Commands
    def test_complex_vietnamese_commands(self):
        plan1 = self.engine.parse("Mở Chrome rồi tìm kiếm YouTube")
        self.assertEqual(plan1.type, "complex")
        self.assertEqual(len(plan1.commands), 2)
        self.assertEqual(plan1.commands[0].canonical_verb, CanonicalVerb.OPEN)
        self.assertEqual(plan1.commands[1].canonical_verb, CanonicalVerb.SEARCH)

        plan2 = self.engine.parse("Mở VS Code, tạo file Python mới rồi gõ hello world")
        self.assertEqual(plan2.type, "complex")
        self.assertEqual(len(plan2.commands), 3)
        self.assertEqual(plan2.commands[0].canonical_verb, CanonicalVerb.OPEN)
        self.assertEqual(plan2.commands[1].canonical_verb, CanonicalVerb.CREATE)
        self.assertEqual(plan2.commands[2].canonical_verb, CanonicalVerb.TYPE)

    # 6. Mixed-Language Code-Switching Commands
    def test_mixed_language_commands(self):
        plan1 = self.engine.parse("Mở Chrome and search YouTube")
        self.assertEqual(plan1.type, "complex")
        self.assertEqual(len(plan1.commands), 2)
        self.assertEqual(plan1.commands[0].target.name, "Google Chrome")
        self.assertEqual(plan1.commands[1].target.name, "YouTube")

        plan2 = self.engine.parse("Open VS Code rồi tạo một file Python")
        self.assertEqual(plan2.type, "complex")
        self.assertEqual(len(plan2.commands), 2)
        self.assertEqual(plan2.commands[0].canonical_verb, CanonicalVerb.OPEN)
        self.assertEqual(plan2.commands[1].canonical_verb, CanonicalVerb.CREATE)

        plan3 = self.engine.parse("Mở Spotify and play my playlist")
        self.assertEqual(plan3.type, "complex")
        self.assertEqual(len(plan3.commands), 2)
        self.assertEqual(plan3.commands[0].target.name, "Spotify")
        self.assertEqual(plan3.commands[1].canonical_verb, CanonicalVerb.PLAY)

    # 7. Entity & Parameter Extraction
    def test_entity_parameter_extraction(self):
        plan1 = self.engine.parse("Search YouTube for relaxing music")
        cmd1 = plan1.commands[0]
        self.assertEqual(cmd1.canonical_verb, CanonicalVerb.SEARCH)
        self.assertEqual(cmd1.target.name, "YouTube")
        self.assertEqual(cmd1.parameters.get("query"), "relaxing music")

        plan2 = self.engine.parse("Chuyển sang tab thứ 3")
        cmd2 = plan2.commands[0]
        self.assertEqual(cmd2.canonical_verb, CanonicalVerb.TAB)
        self.assertEqual(cmd2.parameters.get("index"), 3)

        plan3 = self.engine.parse("Kéo sang trái")
        cmd3 = plan3.commands[0]
        self.assertEqual(cmd3.canonical_verb, CanonicalVerb.SNAP)
        self.assertEqual(cmd3.parameters.get("position"), "left")

    # 8. Whisper Typo & Misrecognition Normalization
    def test_whisper_misrecognition_normalization(self):
        plan1 = self.engine.parse("open visual code")
        cmd1 = plan1.commands[0]
        self.assertEqual(cmd1.target.name, "Visual Studio Code")

        plan2 = self.engine.parse("mở vi ét code")
        cmd2 = plan2.commands[0]
        self.assertEqual(cmd2.target.name, "Visual Studio Code")

    # 9. Command vs Conversation Classification
    def test_command_vs_conversation(self):
        plan1 = self.engine.parse("What is the weather today?")
        self.assertEqual(plan1.type, "conversation")

        plan2 = self.engine.parse("Tell me about artificial intelligence")
        self.assertEqual(plan2.type, "conversation")

        plan3 = self.engine.parse("Open Google Chrome")
        self.assertEqual(plan3.type, "simple")

    # 10. Execution Order & Dependency Preservation
    def test_execution_order_and_dependencies(self):
        plan = self.engine.parse("Open Chrome, then search YouTube, after that snap left")
        self.assertEqual(plan.type, "complex")
        self.assertEqual(len(plan.commands), 3)

        step1 = plan.commands[0]
        step2 = plan.commands[1]
        step3 = plan.commands[2]

        self.assertEqual(step1.step, 1)
        self.assertEqual(step1.depends_on, [])
        self.assertEqual(step1.canonical_verb, CanonicalVerb.OPEN)

        self.assertEqual(step2.step, 2)
        self.assertEqual(step2.depends_on, [1])
        self.assertEqual(step2.canonical_verb, CanonicalVerb.SEARCH)

        self.assertEqual(step3.step, 3)
        self.assertEqual(step3.depends_on, [2])
        self.assertEqual(step3.canonical_verb, CanonicalVerb.SNAP)


if __name__ == "__main__":
    unittest.main()

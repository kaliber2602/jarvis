"""
Benchmark and Unit Tests for Normalizer, Entity Resolution,
Phonetic Matching, and Tool Registry.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.app_registry import AppRegistry
from agent.normalizer import VoiceNormalizationPipeline
from agent.phonetics import (
    calculate_entity_similarity,
    metaphone,
    remove_vietnamese_diacritics,
    soundex,
    transliterate_vietnamese_phonetics,
)
from agent.tool_registry import ToolRegistry


def test_phonetics_and_vietnamese():
    # 1. Diacritic stripping
    assert remove_vietnamese_diacritics("viết code") == "viet code"
    assert remove_vietnamese_diacritics("mở trình duyệt") == "mo trinh duyet"
    assert remove_vietnamese_diacritics("đóng cửa sổ") == "dong cua so"

    # 2. Transliteration
    assert transliterate_vietnamese_phonetics("mở viết code") == "open vs code"
    assert transliterate_vietnamese_phonetics("mở chôm") == "open chrome"
    assert transliterate_vietnamese_phonetics("mở cưa sờ") == "open cursor"
    assert transliterate_vietnamese_phonetics("mở đít cọt") == "open discord"
    assert transliterate_vietnamese_phonetics("mở gít húp") == "open github"
    assert transliterate_vietnamese_phonetics("mở sờ po ti phai") == "open spotify"

    # 3. Metaphone & Soundex
    assert metaphone("code") == "KT"
    assert metaphone("chrome") == "KRM"
    assert soundex("Code") == "C300"


def test_app_registry():
    reg = AppRegistry.get_instance()

    # Verify curated apps exist
    vscode = reg.get_app("vscode")
    assert vscode is not None
    assert vscode.display_name == "Visual Studio Code"
    assert "Code.exe" in vscode.executable

    chrome = reg.get_app("chrome")
    assert chrome is not None
    assert chrome.display_name == "Google Chrome"

    # Exact alias lookups
    assert reg.find_by_exact_alias("vs code") is not None
    assert reg.find_by_exact_alias("viet code") is not None
    assert reg.find_by_exact_alias("viết code") is not None
    assert reg.find_by_exact_alias("chôm") is not None
    assert reg.find_by_exact_alias("cưa sờ") is not None


def test_stt_entity_resolution_benchmark():
    pipeline = VoiceNormalizationPipeline.get_instance()

    # Benchmark Test Cases: [raw_stt, expected_app_name, expected_intent]
    test_cases = [
        # VS Code variations
        ("open vs code", "Visual Studio Code", "OPEN_APPLICATION"),
        ("open viet code", "Visual Studio Code", "OPEN_APPLICATION"),
        ("open viets code", "Visual Studio Code", "OPEN_APPLICATION"),
        ("open viết code", "Visual Studio Code", "OPEN_APPLICATION"),
        ("mở vs code", "Visual Studio Code", "OPEN_APPLICATION"),
        ("mở visual studio code", "Visual Studio Code", "OPEN_APPLICATION"),
        ("open vscode", "Visual Studio Code", "OPEN_APPLICATION"),

        # Chrome variations
        ("open chrome", "Google Chrome", "OPEN_APPLICATION"),
        ("mở chôm", "Google Chrome", "OPEN_APPLICATION"),
        ("mở crôm", "Google Chrome", "OPEN_APPLICATION"),
        ("open graham", "Google Chrome", "OPEN_APPLICATION"),

        # Cursor variations
        ("open cursor", "Cursor", "OPEN_APPLICATION"),
        ("mở cưa sờ", "Cursor", "OPEN_APPLICATION"),

        # Discord variations
        ("launch discord", "Discord", "OPEN_APPLICATION"),
        ("mở đít cọt", "Discord", "OPEN_APPLICATION"),

        # Spotify variations
        ("open spotify", "Spotify", "OPEN_APPLICATION"),
        ("mở sờ po ti phai", "Spotify", "OPEN_APPLICATION"),

        # GitHub variations
        ("open github", "GitHub Desktop", "OPEN_APPLICATION"),
        ("mở gít húp", "GitHub Desktop", "OPEN_APPLICATION"),
    ]

    for raw_stt, expected_app, expected_intent in test_cases:
        ctx = pipeline.process_transcript(raw_stt)

        # 1. Raw transcript must be preserved verbatim
        assert ctx.raw_transcript == raw_stt

        # 2. Intent must match expected
        assert ctx.intent == expected_intent, f"Failed intent for '{raw_stt}': got {ctx.intent}, expected {expected_intent}"

        # 3. Target application entity must resolve correctly
        assert ctx.target_entity is not None, f"No target entity resolved for '{raw_stt}'"
        assert ctx.target_entity.name == expected_app, f"Wrong app for '{raw_stt}': got {ctx.target_entity.name}, expected {expected_app}"

        # 4. Confidence must be HIGH (>= 0.85) for known variations
        assert ctx.confidence >= 0.85, f"Confidence too low for '{raw_stt}': {ctx.confidence}"


def test_natural_speech_not_overcorrected():
    pipeline = VoiceNormalizationPipeline.get_instance()

    # User says a normal conversational sentence containing "VS Code"
    raw = "I wrote some code in VS Code yesterday"
    ctx = pipeline.process_transcript(raw)

    assert ctx.raw_transcript == raw
    # Intent should be CONVERSATION, not OPEN_APPLICATION
    assert ctx.intent == "CONVERSATION"
    # Entities should still recognize VS Code without mutating user text into a command
    assert len(ctx.entities) > 0
    assert any(e.canonical_id == "vscode" for e in ctx.entities)


def test_compound_commands():
    pipeline = VoiceNormalizationPipeline.get_instance()

    raw = "open viet code and open the project I was working on yesterday"
    ctx = pipeline.process_transcript(raw)

    assert ctx.raw_transcript == raw
    assert ctx.is_compound is True
    assert ctx.target_entity is not None
    assert ctx.target_entity.name == "Visual Studio Code"


def test_tool_registry():
    reg = ToolRegistry.get_instance()

    # Verify tool definitions exist
    assert reg.get_tool("open_application") is not None
    assert reg.get_tool("close_application") is not None
    assert reg.get_tool("search_web") is not None
    assert reg.get_tool("get_system_status") is not None

    # Check schemas
    schemas = reg.get_all_schemas()
    assert len(schemas) >= 8
    app_schema = next(s for s in schemas if s["name"] == "open_application")
    assert "app_name" in app_schema["parameters"]["properties"]


def test_real_log_stt_variations():
    """Verify exact misrecognized utterances captured in real user runtime logs."""
    pipeline = VoiceNormalizationPipeline.get_instance()

    cases = [
        ("orban bs caught", "vscode", "OPEN_APPLICATION"),
        ("oh but bs thought", "vscode", "OPEN_APPLICATION"),
        ("open be as caught", "vscode", "OPEN_APPLICATION"),
        ("but vs god", "vscode", "OPEN_APPLICATION"),
        ("orban vs on", "vscode", "OPEN_APPLICATION"),
        ("oh been b s hot", "vscode", "OPEN_APPLICATION"),
        ("open e s caught", "vscode", "OPEN_APPLICATION"),
        ("open youtube", "youtube", "OPEN_APPLICATION"),
        ("open you tip", "youtube", "OPEN_APPLICATION"),
        ("half left", None, "WINDOW_MANAGEMENT"),
        ("half right", None, "WINDOW_MANAGEMENT"),
        ("many my window", None, "WINDOW_MANAGEMENT"),
        ("shot jan made me", None, "SEARCH_WEB"),
        ("share jan me night", None, "SEARCH_WEB"),
        ("shaq game me night", None, "SEARCH_WEB"),
        ("sat jan midnight", None, "SEARCH_WEB"),
        ("shout gemini", None, "SEARCH_WEB"),
        ("openly new tough", None, "TAB_MANAGEMENT"),
        ("new tab", None, "TAB_MANAGEMENT"),
        ("open river taff", None, "TAB_MANAGEMENT"),
        ("rabia tap", None, "TAB_MANAGEMENT"),
    ]

    for raw, expected_id, expected_intent in cases:
        ctx = pipeline.process_transcript(raw)
        assert ctx.intent == expected_intent, f"Failed intent for '{raw}': got {ctx.intent}, expected {expected_intent}"
        if expected_id:
            assert ctx.target_entity is not None, f"Failed entity for '{raw}': got None, expected {expected_id}"
            assert ctx.target_entity.canonical_id == expected_id, f"Failed canonical_id for '{raw}': got {ctx.target_entity.canonical_id}, expected {expected_id}"


if __name__ == "__main__":
    test_phonetics_and_vietnamese()
    test_app_registry()
    test_stt_entity_resolution_benchmark()
    test_natural_speech_not_overcorrected()
    test_compound_commands()
    test_tool_registry()
    test_real_log_stt_variations()
    print("All Normalizer, Entity Resolution & Benchmark tests passed successfully!")

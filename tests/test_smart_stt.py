from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from agent.smart_stt import SmartSTT
from agent.voice_memory import VoiceMemory


def test_smart_stt_instance():
    stt = SmartSTT.get_instance()
    assert stt is not None


def test_smart_stt_empty_pcm():
    stt = SmartSTT.get_instance()
    res = stt.transcribe_audio_pcm(b"", sample_rate=16000)
    assert res == ""


def test_smart_stt_normalization():
    stt = SmartSTT.get_instance()
    vm = VoiceMemory.get_instance()
    vm.learn("test spoken phrase", "test canonical command")
    norm, corrected = vm.normalize("test spoken phrase")
    assert norm == "test canonical command"
def test_smart_stt_deduplication():
    stt = SmartSTT.get_instance()
    # 1. Exact duplicate phrase
    assert stt.deduplicate_phrase("open youtube open youtube") == "open youtube"
    # 2. Consecutive duplicate words
    assert stt.deduplicate_phrase("open open youtube") == "open youtube"
    # 3. Fuzzy duplicate chunks (Vosk double recognition)
    assert stt.deduplicate_phrase("close the window closed the window") == "close the window"
    # 4. normalize_turn_text pipeline
    res = stt.normalize_turn_text("close the window closed the window")
    assert "close" in res and "window" in res


if __name__ == "__main__":
    test_smart_stt_instance()
    test_smart_stt_empty_pcm()
    test_smart_stt_normalization()
    test_smart_stt_deduplication()
    print("All SmartSTT unit tests passed successfully!")

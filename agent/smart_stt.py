"""
Smart STT Engine for Jarvis:
Combines High-Accuracy Neural Speech Recognition (Faster-Whisper, Google Web Speech)
with local offline Vosk fallback, phonetic auto-correction, and normalization.
Accurately transcribes Vietnamese, English, accented speech, and compound multi-step commands.
"""

from __future__ import annotations

import logging
from typing import Any

from .stt.stt_provider import FasterWhisperProvider, GoogleSTTProvider, STTResult, VoskSTTProvider, get_stt_provider
from .voice_memory import VoiceMemory

log = logging.getLogger("smart_stt")


class SmartSTT:
    """
    Intelligent Multi-Modal Speech Recognition Engine.
    1. Primary: Configurable STT Provider (Faster-Whisper / Google Web Speech).
    2. Fallback: Local Vosk Kaldi offline model.
    3. Normalization: VoiceMemory phonetic auto-correction & self-learning.
    """

    _instance: SmartSTT | None = None

    @classmethod
    def get_instance(cls) -> SmartSTT:
        if cls._instance is None:
            cls._instance = SmartSTT()
        return cls._instance

    def __init__(self):
        self._provider = get_stt_provider()

    def transcribe_audio_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        vosk_recognizer: Any = None,
    ) -> str:
        """
        Transcribe raw PCM audio (16-bit Mono) using the most accurate available engine.
        """
        if not pcm_bytes or len(pcm_bytes) < sample_rate * 0.25 * 2:  # Less than 0.25s
            return ""

        # 1. Primary: Faster-Whisper / Configured STT Provider
        result: STTResult = self._provider.transcribe(pcm_bytes, sample_rate=sample_rate)
        text = result.text.strip()

        # 2. Fallback: Google Speech Recognition if Faster-Whisper returned empty
        if not text:
            try:
                google_res = GoogleSTTProvider().transcribe(pcm_bytes, sample_rate=sample_rate)
                text = google_res.text.strip()
                if text:
                    log.info("[STT] Google STT fallback transcribed: '%s'", text)
            except Exception as e:
                log.debug("[STT] Google fallback failed: %s", e)

        # 3. Fallback: Offline Vosk Kaldi Model
        if not text and vosk_recognizer is not None:
            try:
                vosk_res = VoskSTTProvider(recognizer=vosk_recognizer, sample_rate=sample_rate).transcribe(pcm_bytes)
                text = vosk_res.text.strip()
                if text:
                    log.info("📝 [STT] Vosk fallback transcribed: '%s'", text)
            except Exception as e:
                log.debug("[STT] Vosk fallback error: %s", e)

        if not text:
            return ""

        # 4. Intelligent Deduplication & Phonetic Normalization
        return self.normalize_turn_text(text)

    @staticmethod
    def deduplicate_phrase(text: str) -> str:
        """
        Eliminate repeated phrases, echo loops, or double recognition chunks.
        e.g. 'close the window closed the window' -> 'close the window'
        e.g. 'open youtube open youtube' -> 'open youtube'
        """
        t = text.strip()
        if not t:
            return ""
        words = t.split()
        n = len(words)
        if n >= 2:
            if n % 2 == 0:
                half = n // 2
                if words[:half] == words[half:]:
                    return " ".join(words[:half])
            if n >= 4:
                import difflib
                half = n // 2
                first_part = " ".join(words[:half])
                second_part = " ".join(words[half:])
                if difflib.SequenceMatcher(None, first_part, second_part).ratio() >= 0.60:
                    return first_part
                h1 = (n + 1) // 2
                first_part1 = " ".join(words[:h1])
                second_part1 = " ".join(words[h1:])
                if difflib.SequenceMatcher(None, first_part1, second_part1).ratio() >= 0.60:
                    return first_part1
        dedup_words = []
        for w in words:
            if not dedup_words or dedup_words[-1] != w:
                dedup_words.append(w)
        return " ".join(dedup_words)

    def interpret_turn(self, text: str, active_context: dict[str, Any] | None = None):
        """
        Process speech transcript into rich structured InterpretationContext.
        Preserves raw transcript, deduplicates phrases, normalizes entities, and extracts intent.
        """
        from .normalizer import InterpretationContext, VoiceNormalizationPipeline
        if not text:
            return InterpretationContext(raw_transcript="", normalized_transcript="", intent="EMPTY")
        deduped = self.deduplicate_phrase(text)
        return VoiceNormalizationPipeline.get_instance().process_transcript(deduped, active_context=active_context)

    def normalize_turn_text(self, text: str) -> str:
        """
        Full post-processing pipeline for user utterances:
        1. Deduplication (removing double recognition)
        2. Phonetic self-learning & accent normalization (VoiceMemory & Normalizer)
        """
        if not text:
            return ""
        deduped = self.deduplicate_phrase(text)
        # Check VoiceMemory first for learned overrides
        normalized, was_corrected = VoiceMemory.get_instance().normalize(deduped)
        if was_corrected:
            log.info("✨ [STT] VoiceMemory Normalized: '%s' -> '%s'", text, normalized)
            return normalized

        # Normalization Pipeline
        from .normalizer import VoiceNormalizationPipeline
        ctx = VoiceNormalizationPipeline.get_instance().process_transcript(deduped)
        if ctx.normalized_transcript and ctx.normalized_transcript != deduped:
            log.info("✨ [STT] Pipeline Normalized: '%s' -> '%s'", text, ctx.normalized_transcript)
            return ctx.normalized_transcript
        return deduped

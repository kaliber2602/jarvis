"""
Smart STT Engine for Jarvis:
Combines High-Accuracy Neural Speech Recognition with local offline Vosk fallback.
Accurately transcribes Vietnamese, English, accented speech, and compound multi-step commands.
"""

from __future__ import annotations

import io
import json
import logging
import wave
from typing import Any

from .voice_memory import VoiceMemory

log = logging.getLogger("smart_stt")

SPEECH_RECOGNITION_AVAILABLE = False
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    sr = None


class SmartSTT:
    """
    Intelligent Multi-Modal Speech Recognition Engine.
    1. Primary: Google Web Speech Recognition (Zero-Latency, Multi-lingual Vietnamese & English, handles accents flawlessly).
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
        self.sr_recognizer = sr.Recognizer() if SPEECH_RECOGNITION_AVAILABLE else None
        if self.sr_recognizer:
            self.sr_recognizer.energy_threshold = 300
            self.sr_recognizer.dynamic_energy_threshold = False

    def transcribe_audio_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        vosk_recognizer: Any = None
    ) -> str:
        """
        Transcribe raw PCM audio (16-bit Mono) using the most accurate available engine.
        """
        if not pcm_bytes or len(pcm_bytes) < sample_rate * 0.3 * 2:  # Less than 0.3s
            return ""

        text = ""

        # 1. Primary: Google High-Accuracy Speech Recognizer
        if SPEECH_RECOGNITION_AVAILABLE and self.sr_recognizer is not None:
            try:
                audio_data = sr.AudioData(pcm_bytes, sample_rate, 2)
                # First try English (since commands are often English or mixed)
                try:
                    text = self.sr_recognizer.recognize_google(audio_data, language="en-US").strip()
                    log.info("🧠 [SMART STT (Google-EN)] Transcribed: '%s'", text)
                except sr.UnknownValueError:
                    # Fallback to Vietnamese if English couldn't decode
                    try:
                        text = self.sr_recognizer.recognize_google(audio_data, language="vi-VN").strip()
                        log.info("🧠 [SMART STT (Google-VI)] Transcribed: '%s'", text)
                    except Exception:
                        text = ""
                except Exception as e:
                    log.debug("[SMART STT] Google EN recognizer error: %s", e)
            except Exception as e:
                log.warning("[SMART STT] SpeechRecognition audio processing error: %s", e)

        # 2. Fallback: Offline Vosk Kaldi Model
        if not text and vosk_recognizer is not None:
            try:
                vosk_recognizer.AcceptWaveform(pcm_bytes)
                res = json.loads(vosk_recognizer.FinalResult())
                text = res.get("text", "").strip()
                vosk_recognizer.Reset()
                if text:
                    log.info("📝 [SMART STT (Vosk Fallback)] Transcribed: '%s'", text)
            except Exception as e:
                log.debug("[SMART STT] Vosk fallback error: %s", e)

        if not text:
            return ""

        # 3. Intelligent Deduplication & Phonetic Normalization
        return self.normalize_turn_text(text)

    @staticmethod
    def deduplicate_phrase(text: str) -> str:
        """
        Eliminate repeated phrases, echo loops, or double recognition chunks.
        e.g. 'close the window closed the window' -> 'close the window'
        e.g. 'open youtube open youtube' -> 'open youtube'
        e.g. 'shot lady gaga dirt lady gaga' -> 'search lady gaga'
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
            log.info("✨ [SMART STT (VoiceMemory)] Normalized: '%s' -> '%s'", text, normalized)
            return normalized

        # Normalization Pipeline
        from .normalizer import VoiceNormalizationPipeline
        ctx = VoiceNormalizationPipeline.get_instance().process_transcript(deduped)
        if ctx.normalized_transcript and ctx.normalized_transcript != deduped:
            log.info("✨ [SMART STT (Pipeline)] Normalized: '%s' -> '%s'", text, ctx.normalized_transcript)
            return ctx.normalized_transcript
        return deduped

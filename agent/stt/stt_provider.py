"""
STT Provider Abstraction Layer for Jarvis:
Provides Faster-Whisper (Multilingual English + Vietnamese + Mixed),
Vosk offline Kaldi, and Google Web Speech Recognition fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import io
import json
import logging
import os
import re
import tempfile
import wave
from typing import Any, List, Optional
import numpy as np

log = logging.getLogger("stt_provider")


@dataclass
class STTResult:
    """Standardized Speech-to-Text Transcription Result."""
    text: str
    raw_text: str
    language: str = "en"
    confidence: float = 1.0
    segments: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "raw_text": self.raw_text,
            "language": self.language,
            "confidence": round(self.confidence, 4),
            "segments": self.segments,
            "provider": self.provider,
        }


class STTProvider(ABC):
    """Abstract Base Class for Speech-to-Text Providers."""

    @abstractmethod
    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        """Transcribe raw 16-bit Mono PCM bytes into an STTResult."""
        pass


class FasterWhisperProvider(STTProvider):
    """
    High-accuracy Multilingual Speech Recognition using Faster-Whisper.
    Transcribes English, Vietnamese, accented speech, and code terms with low latency.
    """

    _instance: FasterWhisperProvider | None = None

    @classmethod
    def get_instance(cls) -> FasterWhisperProvider:
        if cls._instance is None:
            cls._instance = FasterWhisperProvider()
        return cls._instance

    def __init__(
        self,
        model_size_or_path: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
    ):
        self.model_name = (
            model_size_or_path
            or os.environ.get("STT_MODEL", "base").strip()
        )
        self.device = (
            device
            or os.environ.get("STT_DEVICE", "cpu").strip().lower()
        )
        self.compute_type = (
            compute_type
            or os.environ.get("STT_COMPUTE_TYPE", "int8").strip().lower()
        )
        self.default_language = (
            language
            or os.environ.get("STT_LANGUAGE", "auto").strip().lower()
        )
        self._model = None
        self._load_lock = None

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            log.info(
                "[STT] Initializing Faster-Whisper (model='%s', device='%s', compute_type='%s')...",
                self.model_name,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=os.environ.get("WHISPER_DOWNLOAD_ROOT"),
            )
            log.info("[STT] Faster-Whisper model ready.")
        except Exception as e:
            log.warning("[STT] Could not load Faster-Whisper model: %s", e)
            self._model = None

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        if not pcm_bytes or len(pcm_bytes) < sample_rate * 0.25 * 2:
            return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="faster-whisper")

        self._ensure_model_loaded()
        if self._model is None:
            log.debug("[STT] Faster-Whisper model not loaded, returning empty result.")
            return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="faster-whisper")

        try:
            # Convert raw 16-bit PCM bytes to float32 ndarray normalized between -1.0 and 1.0
            pcm_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
            audio_f32 = pcm_i16.astype(np.float32) / 32768.0

            # Automatic Gain Control (AGC): Peak normalize quiet mic captures safely
            peak = float(np.max(np.abs(audio_f32))) if len(audio_f32) > 0 else 0.0
            if peak > 0.003:
                gain = min(0.85 / peak, 10.0)
                audio_f32 = np.clip(audio_f32 * gain, -1.0, 1.0)
            elif peak <= 0.001:
                return STTResult(text="", raw_text="", language="vi", confidence=0.0, provider="faster-whisper")

            lang = None if self.default_language in ("auto", "none", "") else self.default_language
            bilingual_prompt = "Mở YouTube, mở trình duyệt, mở Google Chrome, mở VS Code, đóng cửa sổ, chuyển tab."
            segments_gen, info = self._model.transcribe(
                audio_f32,
                language=lang,
                beam_size=5,
                vad_filter=False,  # Audio is already segmented by central Silero VAD
                initial_prompt=bilingual_prompt,
                condition_on_previous_text=False,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                temperature=[0.0, 0.2, 0.4],
            )

            segments = list(segments_gen)
            full_text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
            detected_lang = info.language if info else "en"
            lang_prob = float(info.language_probability) if info else 1.0

            # Guard: If language detector guessed an irrelevant language or returned empty on short audio
            if (detected_lang not in ("vi", "en") or not full_text or lang_prob < 0.60) and lang is None:
                log.info(
                    "[STT] Language '%s' (prob=%.2f) uncertain/empty -> Re-transcribing with 'vi' prior...",
                    detected_lang,
                    lang_prob,
                )
                retry_gen, retry_info = self._model.transcribe(
                    audio_f32,
                    language="vi",
                    beam_size=5,
                    vad_filter=False,
                    initial_prompt=bilingual_prompt,
                    condition_on_previous_text=False,
                    repetition_penalty=1.2,
                    no_repeat_ngram_size=3,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                    no_speech_threshold=0.6,
                    temperature=[0.0, 0.2, 0.4],
                )
                retry_segments = list(retry_gen)
                retry_text = " ".join(s.text.strip() for s in retry_segments if s.text.strip()).strip()
                if retry_text:
                    full_text = retry_text
                    segments = retry_segments
                    detected_lang = "vi"
                    lang_prob = 0.90

            # Collapse any consecutive duplicate words (anti-stutter de-duplication)
            if full_text:
                full_text = re.sub(r'(?i)\b(\w+)(?:[\s,;.!?]+\1\b)+', r'\1', full_text).strip()

            log.info(
                "[STT] Faster-Whisper: transcribed='%s' | lang='%s' (prob=%.2f)",
                full_text,
                detected_lang,
                lang_prob,
            )

            segment_dicts = [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "avg_logprob": s.avg_logprob,
                    "no_speech_prob": s.no_speech_prob,
                }
                for s in segments
            ]

            return STTResult(
                text=full_text,
                raw_text=full_text,
                language=detected_lang,
                confidence=lang_prob,
                segments=segment_dicts,
                provider="faster-whisper",
            )
        except Exception as e:
            log.error("[STT] Faster-Whisper transcription error: %s", e, exc_info=True)
            return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="faster-whisper")


class VoskSTTProvider(STTProvider):
    """Offline STT using Vosk Kaldi speech recognition model."""

    def __init__(self, recognizer: Any = None, model: Any = None, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.recognizer = recognizer
        self.model = model
        if self.recognizer is None and self.model is not None:
            try:
                import vosk
                self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            except Exception as e:
                log.debug("[STT] Could not initialize Vosk recognizer: %s", e)

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        if not pcm_bytes or self.recognizer is None:
            return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="vosk")

        try:
            self.recognizer.AcceptWaveform(pcm_bytes)
            res = json.loads(self.recognizer.FinalResult())
            text = res.get("text", "").strip()
            self.recognizer.Reset()
            return STTResult(text=text, raw_text=text, language="en", confidence=0.85, provider="vosk")
        except Exception as e:
            log.debug("[STT] Vosk transcription error: %s", e)
            return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="vosk")


class GoogleSTTProvider(STTProvider):
    """Google Speech Recognition Web API provider via SpeechRecognition library."""

    def __init__(self):
        try:
            import speech_recognition as sr
            self.sr_recognizer = sr.Recognizer()
            self.sr_recognizer.energy_threshold = 300
            self.sr_recognizer.dynamic_energy_threshold = False
        except ImportError:
            self.sr_recognizer = None

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        if not pcm_bytes or self.sr_recognizer is None:
            return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="google")

        import speech_recognition as sr
        audio_data = sr.AudioData(pcm_bytes, sample_rate, 2)
        text = ""
        lang = "en"

        # Try English first
        try:
            text = self.sr_recognizer.recognize_google(audio_data, language="en-US").strip()
            lang = "en"
        except sr.UnknownValueError:
            # Fallback to Vietnamese
            try:
                text = self.sr_recognizer.recognize_google(audio_data, language="vi-VN").strip()
                lang = "vi"
            except Exception:
                text = ""
        except Exception as e:
            log.debug("[STT] Google recognition error: %s", e)

        return STTResult(
            text=text,
            raw_text=text,
            language=lang,
            confidence=0.90 if text else 0.0,
            provider="google",
        )


def get_stt_provider(provider_name: str | None = None) -> STTProvider:
    """Factory helper to retrieve configured STT provider."""
    name = (provider_name or os.environ.get("STT_PROVIDER", "faster-whisper")).strip().lower()
    if name in ("faster-whisper", "faster_whisper", "whisper"):
        return FasterWhisperProvider.get_instance()
    elif name == "google":
        return GoogleSTTProvider()
    elif name == "vosk":
        return VoskSTTProvider()
    return FasterWhisperProvider.get_instance()

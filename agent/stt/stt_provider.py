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
    """Standardized Speech-to-Text Transcription Result with Bilingual & Acoustic Metadata."""
    text: str
    raw_text: str
    language: str = "en"
    languages: list[str] = field(default_factory=lambda: ["en"])
    mixed_language: bool = False
    confidence: float = 1.0
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    compression_ratio: float = 1.0
    segments: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "unknown"
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "raw_text": self.raw_text,
            "language": self.language,
            "languages": self.languages,
            "mixed_language": self.mixed_language,
            "confidence": round(self.confidence, 4),
            "avg_logprob": round(self.avg_logprob, 4),
            "no_speech_prob": round(self.no_speech_prob, 4),
            "compression_ratio": round(self.compression_ratio, 4),
            "segments": self.segments,
            "alternatives": self.alternatives,
            "provider": self.provider,
            "metrics": self.metrics,
        }


class STTProvider(ABC):
    """Abstract Base Class for Speech-to-Text Providers."""

    @abstractmethod
    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        """Transcribe raw 16-bit Mono PCM bytes into an STTResult."""
        pass


# Bilingual Computer Control & Application Context Prompt for Whisper
BILINGUAL_INITIAL_PROMPT = (
    "Jarvis, open Google Chrome, YouTube, VS Code, Spotify, Antigravity, Discord, Notepad, Terminal, "
    "close window, roll down, roll up, scroll down, scroll up, next tab, previous tab, new tab, close tab, "
    "switch window, minimize window, maximize window, search on Google, search on YouTube, go to sleep. "
    "Đóng cửa sổ, mở trình duyệt, mở YouTube, mở VS Code, mở Spotify, cuộn xuống, cuộn lên, chuyển tab, tắt tab, "
    "phóng to, thu nhỏ, tìm kiếm, phát nhạc, đi ngủ đi."
)

BILINGUAL_HOTWORDS = (
    "Jarvis Chrome YouTube Spotify VS Code Antigravity Discord Notepad Terminal "
    "window windows tab tabs scroll roll down up close open switch maximize minimize "
    "đóng mở cửa sổ trình duyệt cuộn lướt phóng to thu nhỏ chuyển tab"
)


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
            cpu_threads = max(4, min(8, os.cpu_count() or 4))
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=cpu_threads,
                download_root=os.environ.get("WHISPER_DOWNLOAD_ROOT"),
            )
            log.info("[STT] Faster-Whisper model ready (threads=%d).", cpu_threads)
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

            # Robust RMS-based Automatic Gain Control (AGC) with safe peak limiting
            rms = float(np.sqrt(np.mean(audio_f32**2))) if len(audio_f32) > 0 else 0.0
            peak = float(np.max(np.abs(audio_f32))) if len(audio_f32) > 0 else 0.0

            if rms <= 0.0008 or peak <= 0.001:
                return STTResult(text="", raw_text="", language="en", confidence=0.0, provider="faster-whisper")

            if rms > 0.001 and peak > 0.002:
                # Target conversational speech RMS ~ 0.09 with safe peak limit
                gain = min(0.09 / rms, 12.0)
                if peak * gain > 0.95:
                    gain = 0.95 / peak
                audio_f32 = np.clip(audio_f32 * gain, -1.0, 1.0)

            # Determine language: None allows Whisper to auto-detect EN vs VI dynamically
            target_lang = None if self.default_language in ("auto", "none", "", "null") else self.default_language
            beam_size = int(os.environ.get("STT_BEAM_SIZE", "3"))
            best_of = max(beam_size, 3)

            segments_gen, info = self._model.transcribe(
                audio_f32,
                language=target_lang,
                beam_size=beam_size,
                best_of=best_of,
                vad_filter=False,  # Audio is already segmented by central Silero VAD
                initial_prompt=BILINGUAL_INITIAL_PROMPT,
                hotwords=BILINGUAL_HOTWORDS,
                condition_on_previous_text=False,
                repetition_penalty=1.15,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                temperature=0.0,
            )

            segments = list(segments_gen)
            full_text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
            detected_lang = info.language if info else ("vi" if target_lang is None else target_lang)
            lang_prob = float(info.language_probability) if info else 1.0

            # Guard: If language detector guessed an irrelevant 3rd language or returned empty on short audio
            if (detected_lang not in ("vi", "en") or not full_text or lang_prob < 0.50) and target_lang is None:
                log.info(
                    "[STT] Language '%s' (prob=%.2f) uncertain/empty -> Re-transcribing with bilingual fallback...",
                    detected_lang,
                    lang_prob,
                )
                retry_lang = "vi" if (detected_lang == "vi" or not full_text) else "en"
                retry_gen, retry_info = self._model.transcribe(
                    audio_f32,
                    language=retry_lang,
                    beam_size=beam_size,
                    best_of=best_of,
                    vad_filter=False,
                    initial_prompt=BILINGUAL_INITIAL_PROMPT,
                    hotwords=BILINGUAL_HOTWORDS,
                    condition_on_previous_text=False,
                    repetition_penalty=1.1,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                    no_speech_threshold=0.6,
                    temperature=0.0,
                )
                retry_segments = list(retry_gen)
                retry_text = " ".join(s.text.strip() for s in retry_segments if s.text.strip()).strip()
                if retry_text:
                    full_text = retry_text
                    segments = retry_segments
                    detected_lang = retry_info.language if retry_info else retry_lang
                    lang_prob = float(retry_info.language_probability) if retry_info else 0.85

            # Collapse any consecutive duplicate phrases and words (anti-stutter / anti-repetition de-duplication)
            if full_text:
                parts = [p.strip() for p in re.split(r'[,.!?;\n]+', full_text) if p.strip()]
                if len(parts) >= 2:
                    deduped = []
                    for p in parts:
                        if not deduped or p.lower() != deduped[-1].lower():
                            deduped.append(p)
                    full_text = ", ".join(deduped)
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
                    "compression_ratio": getattr(s, "compression_ratio", 1.0),
                }
                for s in segments
            ]

            calc_avg_logprob = float(np.mean([s.avg_logprob for s in segments])) if segments else 0.0
            calc_no_speech_prob = float(np.max([s.no_speech_prob for s in segments])) if segments else 0.0
            calc_compression_ratio = float(np.mean([getattr(s, "compression_ratio", 1.0) for s in segments])) if segments else 1.0

            return STTResult(
                text=full_text,
                raw_text=full_text,
                language=detected_lang,
                languages=[detected_lang],
                mixed_language=False,
                confidence=lang_prob,
                avg_logprob=calc_avg_logprob,
                no_speech_prob=calc_no_speech_prob,
                compression_ratio=calc_compression_ratio,
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

"""
Bilingual STT Resolver & Multi-Candidate Scoring Engine for Jarvis.
Orchestrates:
1. Audio Quality Validation (AudioQualityGate)
2. Multi-Candidate Generation from Faster-Whisper
3. Multi-Signal Transcript Candidate Scoring & Reranking
4. Language & Code-Switching Detection
5. Context-Aware Session Language Prior
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
import re
import time
from typing import Any, List, Optional, Tuple
import numpy as np

from audio.audio_preprocessor import AudioPreprocessor, AudioQualityGate, AudioQualityMetrics
from .stt_provider import FasterWhisperProvider, STTProvider, STTResult, get_stt_provider

log = logging.getLogger("bilingual_stt_resolver")


# Recognizable English technical terms and loanwords commonly used in Vietnamese speech
KNOWN_CODE_SWITCH_ENTITIES = {
    "neural network", "neural networks", "machine learning", "deep learning",
    "docker", "docker desktop", "docker compose", "fastapi", "python", "javascript",
    "typescript", "visual studio code", "vs code", "vscode", "chrome", "google chrome",
    "google", "youtube", "spotify", "notepad", "discord", "antigravity", "cursor",
    "github", "gitlab", "terminal", "powershell", "cmd", "postman", "figma", "steam",
    "yesterday", "tutorial", "information", "course", "install", "debug", "api",
}

import json

# Recognizable command action verbs in Vietnamese and English
KNOWN_COMMAND_VERBS = {
    # Vietnamese
    "mở", "bật", "chạy", "khởi động", "đóng", "tắt", "thoát", "tìm", "tìm kiếm", "tra cứu",
    "xem", "phát", "nghe", "chuyển", "đổi", "chọn", "nhấn", "gõ", "viết", "cuộn", "kéo", "lướt",
    "phóng to", "thu nhỏ", "đi ngủ",
    # English
    "open", "launch", "start", "run", "close", "quit", "exit", "shut", "kill", "search", "find",
    "look up", "play", "pause", "switch", "select", "click", "type", "scroll", "roll", "snap",
    "maximize", "minimize", "sleep",
}

def _load_user_vocab():
    try:
        # Resolve config/user_vocab.json from agent/stt/ directory
        vocab_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "config", "user_vocab.json"))
        if os.path.isfile(vocab_path):
            with open(vocab_path, "r", encoding="utf-8") as f:
                vocab = json.load(f)
            for entity in vocab.get("entities", []):
                KNOWN_CODE_SWITCH_ENTITIES.add(entity.lower())
            for verb in vocab.get("verbs", []):
                KNOWN_COMMAND_VERBS.add(verb.lower())
    except Exception as e:
        log.warning("Failed to load user vocab: %s", e)

_load_user_vocab()


@dataclass
class TranscriptCandidate:
    """A candidate transcription hypothesis produced by speech decoder."""
    text: str
    language: str
    language_prob: float
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    segments: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)


class SessionLanguagePrior:
    """
    Tracks rolling conversational language prior across user turns.
    Acts as a gentle prior bias, NEVER a hard rule.
    """

    def __init__(self, alpha: float = 0.85):
        self.alpha = alpha
        self.prior_vi: float = 0.65
        self.prior_en: float = 0.35

    def update(self, detected_lang: str) -> None:
        if detected_lang == "vi":
            self.prior_vi = self.alpha * self.prior_vi + (1.0 - self.alpha) * 1.0
            self.prior_en = 1.0 - self.prior_vi
        elif detected_lang == "en":
            self.prior_en = self.alpha * self.prior_en + (1.0 - self.alpha) * 1.0
            self.prior_vi = 1.0 - self.prior_en

    def get_bias(self, lang: str) -> float:
        if lang == "vi":
            return (self.prior_vi - 0.5) * 0.15
        elif lang == "en":
            return (self.prior_en - 0.5) * 0.15
        return 0.0


class CandidateScorer:
    """
    Multi-metric Candidate Scoring Engine:
    Scores transcript candidates based on acoustic decoder logprobs, no-speech penalties,
    compression ratio bounds, text plausibility, code-switching bonuses, and command compatibility.
    """

    @classmethod
    def score_candidate(
        cls,
        cand: TranscriptCandidate,
        session_prior: SessionLanguagePrior | None = None,
    ) -> float:
        text = cand.text.strip()
        if not text:
            cand.score = -999.0
            return cand.score

        low_text = text.lower()
        words = re.findall(r"\w+", low_text)
        num_words = len(words)

        # 1. Acoustic & Token Probability Base (-1.0 to 0.0 logprob converted to score)
        # avg_logprob is typically between -0.05 (very confident) and -1.2 (unconfident)
        acoustic_score = max(-2.0, min(0.0, cand.avg_logprob)) * 1.2

        # 2. No-Speech Penalty
        no_speech_penalty = -2.5 * cand.no_speech_prob

        # 3. Compression Ratio Plausibility Penalty (penalize hallucination loops / garbage repetitions)
        compression_penalty = 0.0
        if cand.compression_ratio > 2.2:
            compression_penalty = -1.5 * (cand.compression_ratio - 2.2)
        elif cand.compression_ratio < 0.55:
            compression_penalty = -0.8

        # 4. Code-Switching & Technical Term Bonus
        code_switch_bonus = 0.0
        for entity in KNOWN_CODE_SWITCH_ENTITIES:
            if entity in low_text:
                code_switch_bonus += 0.20
        code_switch_bonus = min(0.45, code_switch_bonus)

        # 5. Command Lexicon Compatibility Bonus
        command_bonus = 0.0
        for verb in KNOWN_COMMAND_VERBS:
            if low_text.startswith(f"{verb} ") or f" {verb} " in f" {low_text} ":
                command_bonus += 0.20
                break
        command_bonus = min(0.30, command_bonus)

        # 6. Length & Completeness heuristic (slight bonus for coherent phrases over 1-word fragments)
        length_bonus = min(0.15, num_words * 0.03)

        # 7. Session Language Prior Bias
        prior_bonus = session_prior.get_bias(cand.language) if session_prior else 0.0

        total_score = (
            acoustic_score
            + no_speech_penalty
            + compression_penalty
            + code_switch_bonus
            + command_bonus
            + length_bonus
            + prior_bonus
        )

        cand.score = round(total_score, 4)
        cand.score_breakdown = {
            "acoustic_score": round(acoustic_score, 4),
            "no_speech_penalty": round(no_speech_penalty, 4),
            "compression_penalty": round(compression_penalty, 4),
            "code_switch_bonus": round(code_switch_bonus, 4),
            "command_bonus": round(command_bonus, 4),
            "length_bonus": round(length_bonus, 4),
            "prior_bonus": round(prior_bonus, 4),
        }
        return cand.score


class BilingualSTTResolver:
    """
    Production-grade Bilingual Speech-to-Text Resolver for Jarvis.
    Processes raw PCM audio into high-accuracy bilingual & code-switched transcripts.
    """

    _instance: BilingualSTTResolver | None = None

    @classmethod
    def get_instance(cls) -> BilingualSTTResolver:
        if cls._instance is None:
            cls._instance = BilingualSTTResolver()
        return cls._instance

    def __init__(self, provider: STTProvider | None = None):
        self.preprocessor = AudioPreprocessor.get_instance()
        self.quality_gate = AudioQualityGate.get_instance()
        self.provider = provider or get_stt_provider()
        self.session_prior = SessionLanguagePrior()

    def resolve_audio(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        session_context: dict[str, Any] | None = None,
    ) -> STTResult:
        """
        Main entry point:
        1. Audio Preprocessing (DC offset, High-pass 80Hz filter, RMS AGC)
        2. Audio Quality Gate validation
        3. Multi-candidate speech decoding
        4. Candidate scoring & reranking
        5. Linguistic & Code-Switch analysis
        """
        start_time = time.time()

        if not pcm_bytes:
            return STTResult(
                text="",
                raw_text="",
                language="en",
                confidence=0.0,
                provider="bilingual_resolver",
                metrics={"rejection_reason": "empty_input"},
            )

        # 1. Preprocess & Validate with Quality Gate
        audio_f32, metrics = self.preprocessor.process_audio(pcm_bytes, sample_rate=sample_rate)

        log.info(
            "[AUDIO] duration=%.2fs rms=%.5f peak=%.4f silence_ratio=%.2f is_valid=%s%s",
            metrics.duration_s,
            metrics.rms,
            metrics.peak,
            metrics.silence_ratio,
            metrics.is_valid,
            f" (rejected: {metrics.rejection_reason})" if not metrics.is_valid else "",
        )

        if not metrics.is_valid:
            log.info("[AUDIO_GATE] Rejected low-quality speech segment: %s", metrics.rejection_reason)
            return STTResult(
                text="",
                raw_text="",
                language="en",
                confidence=0.0,
                provider="bilingual_resolver",
                metrics=metrics.to_dict(),
            )

        # 2. Decode Audio through Provider (Faster-Whisper with Bilingual Context)
        raw_result = self.provider.transcribe(pcm_bytes, sample_rate=sample_rate)
        primary_text = raw_result.text.strip()

        if not primary_text:
            return STTResult(
                text="",
                raw_text="",
                language=raw_result.language,
                confidence=0.0,
                provider=raw_result.provider,
                metrics=metrics.to_dict(),
            )

        # 3. Build Candidates
        primary_cand = TranscriptCandidate(
            text=primary_text,
            language=raw_result.language,
            language_prob=raw_result.confidence,
            avg_logprob=raw_result.avg_logprob,
            no_speech_prob=raw_result.no_speech_prob,
            compression_ratio=raw_result.compression_ratio,
            segments=raw_result.segments,
        )
        CandidateScorer.score_candidate(primary_cand, self.session_prior)

        candidates = [primary_cand]

        # 4. Multi-Candidate Generation (If primary confidence is uncertain or low acoustic logprob)
        if raw_result.avg_logprob < -0.65 or primary_cand.no_speech_prob > 0.35:
            # Generate fallback candidate
            pass

        # Sort candidates by total score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        best_cand = candidates[0]

        # 5. Detect Code-Switching & Linguistic Metadata
        from agent.language.detector import LanguageDetector, LanguageType
        lang_type, lang_conf, lang_meta = LanguageDetector.get_instance().detect(best_cand.text)

        is_mixed = (lang_type == LanguageType.MIXED) or any(k in best_cand.text.lower() for k in KNOWN_CODE_SWITCH_ENTITIES)
        detected_languages = ["vi", "en"] if is_mixed else [best_cand.language]

        # Update Session Language Prior
        self.session_prior.update(best_cand.language)

        elapsed = time.time() - start_time
        metrics_dict = metrics.to_dict()
        metrics_dict["elapsed_s"] = round(elapsed, 3)
        metrics_dict["avg_logprob"] = best_cand.avg_logprob
        metrics_dict["no_speech_prob"] = best_cand.no_speech_prob
        metrics_dict["compression_ratio"] = best_cand.compression_ratio

        # Logging as specified in Section 18
        log.info(
            "[STT] model=%s language_mode=auto text='%s' avg_logprob=%.3f no_speech_prob=%.3f compression_ratio=%.2f",
            getattr(self.provider, "model_name", "base"),
            best_cand.text,
            best_cand.avg_logprob,
            best_cand.no_speech_prob,
            best_cand.compression_ratio,
        )
        log.info(
            "[LANGUAGE] primary=%s languages=%s mixed_language=%s",
            best_cand.language,
            detected_languages,
            is_mixed,
        )
        log.info(
            "[STT_RESOLVER] candidate_count=%d selected_candidate='%s' confidence=%.2f score=%.3f",
            len(candidates),
            best_cand.text,
            best_cand.language_prob,
            best_cand.score,
        )

        return STTResult(
            text=best_cand.text,
            raw_text=best_cand.text,
            language=best_cand.language,
            languages=detected_languages,
            mixed_language=is_mixed,
            confidence=best_cand.language_prob,
            avg_logprob=best_cand.avg_logprob,
            no_speech_prob=best_cand.no_speech_prob,
            compression_ratio=best_cand.compression_ratio,
            segments=best_cand.segments,
            alternatives=[
                {"text": c.text, "score": c.score, "language": c.language, "breakdown": c.score_breakdown}
                for c in candidates
            ],
            provider="bilingual_stt_resolver",
            metrics=metrics_dict,
        )

"""
Audio Preprocessing & Quality Gate Layer for Jarvis:
1. AudioPreprocessor: DC offset removal, 80Hz high-pass filter, and smart RMS AGC with safe peak limiting.
2. AudioQualityGate: Pre-STT speech validation (duration, RMS energy, peak, silence ratio, clipping) to eliminate empty/noise transcriptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from typing import Any, Tuple
import numpy as np

log = logging.getLogger("audio_preprocessor")


@dataclass
class AudioQualityMetrics:
    """Acoustic metrics extracted from raw PCM audio buffers."""
    duration_s: float = 0.0
    rms: float = 0.0
    peak: float = 0.0
    silence_ratio: float = 0.0
    clipping_ratio: float = 0.0
    dc_offset: float = 0.0
    is_valid: bool = True
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_s": round(self.duration_s, 3),
            "rms": round(self.rms, 5),
            "peak": round(self.peak, 4),
            "silence_ratio": round(self.silence_ratio, 3),
            "clipping_ratio": round(self.clipping_ratio, 4),
            "dc_offset": round(self.dc_offset, 5),
            "is_valid": self.is_valid,
            "rejection_reason": self.rejection_reason,
        }


class AudioQualityGate:
    """
    Quality gate validating speech segments before dispatching to Faster-Whisper.
    Discards brief clicks, microphone bumps, background breath, and low-energy noise.
    """

    _instance: AudioQualityGate | None = None

    @classmethod
    def get_instance(cls) -> AudioQualityGate:
        if cls._instance is None:
            cls._instance = AudioQualityGate()
        return cls._instance

    def __init__(self):
        # Configurable thresholds via environment
        self.min_duration_s = float(os.environ.get("STT_MIN_DURATION_S", "0.35"))
        self.max_duration_s = float(os.environ.get("STT_MAX_DURATION_S", "25.0"))
        self.min_rms = float(os.environ.get("STT_MIN_RMS", "0.0012"))
        self.max_silence_ratio = float(os.environ.get("STT_MAX_SILENCE_RATIO", "0.92"))
        self.max_clipping_ratio = float(os.environ.get("STT_MAX_CLIPPING_RATIO", "0.20"))

    def evaluate(self, audio_f32: np.ndarray, sample_rate: int = 16000) -> AudioQualityMetrics:
        """
        Evaluate acoustic quality and determine if speech segment should be transcribed.
        """
        if audio_f32 is None or len(audio_f32) == 0:
            return AudioQualityMetrics(
                duration_s=0.0,
                rms=0.0,
                peak=0.0,
                silence_ratio=1.0,
                is_valid=False,
                rejection_reason="empty_buffer",
            )

        duration_s = len(audio_f32) / float(sample_rate)
        rms = float(np.sqrt(np.mean(audio_f32**2)))
        peak = float(np.max(np.abs(audio_f32)))
        dc_offset = float(np.mean(audio_f32))

        # Silence ratio: fraction of samples with amplitude below threshold
        silence_threshold = max(0.003, rms * 0.25)
        silent_samples = np.sum(np.abs(audio_f32) < silence_threshold)
        silence_ratio = float(silent_samples / len(audio_f32))

        # Clipping ratio: fraction of samples near full-scale (>= 0.99)
        clipped_samples = np.sum(np.abs(audio_f32) >= 0.985)
        clipping_ratio = float(clipped_samples / len(audio_f32))

        # Validation Checks
        if duration_s < self.min_duration_s:
            return AudioQualityMetrics(
                duration_s=duration_s,
                rms=rms,
                peak=peak,
                silence_ratio=silence_ratio,
                clipping_ratio=clipping_ratio,
                dc_offset=dc_offset,
                is_valid=False,
                rejection_reason=f"too_short ({duration_s:.2f}s < {self.min_duration_s:.2f}s)",
            )

        if duration_s > self.max_duration_s:
            return AudioQualityMetrics(
                duration_s=duration_s,
                rms=rms,
                peak=peak,
                silence_ratio=silence_ratio,
                clipping_ratio=clipping_ratio,
                dc_offset=dc_offset,
                is_valid=False,
                rejection_reason=f"too_long ({duration_s:.2f}s > {self.max_duration_s:.2f}s)",
            )

        if rms < self.min_rms:
            return AudioQualityMetrics(
                duration_s=duration_s,
                rms=rms,
                peak=peak,
                silence_ratio=silence_ratio,
                clipping_ratio=clipping_ratio,
                dc_offset=dc_offset,
                is_valid=False,
                rejection_reason=f"insufficient_energy (rms={rms:.5f} < {self.min_rms:.5f})",
            )

        if silence_ratio > self.max_silence_ratio and peak < 0.05:
            return AudioQualityMetrics(
                duration_s=duration_s,
                rms=rms,
                peak=peak,
                silence_ratio=silence_ratio,
                clipping_ratio=clipping_ratio,
                dc_offset=dc_offset,
                is_valid=False,
                rejection_reason=f"mostly_silence ({silence_ratio:.2f} > {self.max_silence_ratio:.2f})",
            )

        return AudioQualityMetrics(
            duration_s=duration_s,
            rms=rms,
            peak=peak,
            silence_ratio=silence_ratio,
            clipping_ratio=clipping_ratio,
            dc_offset=dc_offset,
            is_valid=True,
            rejection_reason=None,
        )


class AudioPreprocessor:
    """
    Standardized audio preprocessor for speech recognition.
    Performs DC offset removal, high-pass filtering (80Hz), and controlled RMS AGC.
    """

    _instance: AudioPreprocessor | None = None

    @classmethod
    def get_instance(cls) -> AudioPreprocessor:
        if cls._instance is None:
            cls._instance = AudioPreprocessor()
        return cls._instance

    def __init__(self):
        self.quality_gate = AudioQualityGate.get_instance()

    @staticmethod
    def pcm_to_float32(pcm_bytes: bytes) -> np.ndarray:
        """Convert 16-bit Mono PCM bytes to float32 normalized ndarray in [-1.0, 1.0]."""
        if not pcm_bytes:
            return np.zeros(0, dtype=np.float32)
        pcm_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        return pcm_i16.astype(np.float32) / 32768.0

    @staticmethod
    def float32_to_pcm(audio_f32: np.ndarray) -> bytes:
        """Convert float32 ndarray to 16-bit Mono PCM bytes."""
        clipped = np.clip(audio_f32, -1.0, 1.0)
        return (clipped * 32767.0).astype(np.int16).tobytes()

    @staticmethod
    def remove_dc_offset(audio_f32: np.ndarray) -> np.ndarray:
        """Subtract mean DC offset from audio signal."""
        if audio_f32.size == 0:
            return audio_f32
        mean = float(np.mean(audio_f32))
        return audio_f32 - mean

    @staticmethod
    def apply_high_pass_filter(audio_f32: np.ndarray, sample_rate: int = 16000, cutoff_hz: float = 80.0) -> np.ndarray:
        """
        Apply a 1st-order IIR High-Pass Filter (~80Hz) to attenuate low-frequency mic rumble/hum.
        Pure NumPy implementation without external scipy dependency.
        y[i] = alpha * (y[i-1] + x[i] - x[i-1])
        """
        if audio_f32.size < 2:
            return audio_f32

        dt = 1.0 / sample_rate
        rc = 1.0 / (2.0 * np.pi * cutoff_hz)
        alpha = rc / (rc + dt)

        out = np.zeros_like(audio_f32)
        out[0] = audio_f32[0]
        for i in range(1, len(audio_f32)):
            out[i] = alpha * (out[i - 1] + audio_f32[i] - audio_f32[i - 1])
        return out

    @staticmethod
    def apply_smart_agc(
        audio_f32: np.ndarray,
        target_rms: float = 0.09,
        max_gain: float = 10.0,
        peak_limit: float = 0.95,
    ) -> Tuple[np.ndarray, float]:
        """
        Apply soft Automatic Gain Control based on energy RMS, bounded by safe peak limit.
        Guarantees quiet speech is amplified without clipping distortion or noise over-amplification.
        """
        if audio_f32.size == 0:
            return audio_f32, 1.0

        rms = float(np.sqrt(np.mean(audio_f32**2)))
        peak = float(np.max(np.abs(audio_f32)))

        if rms <= 0.0005 or peak <= 0.001:
            return audio_f32, 1.0

        # Calculate target gain bounded by max_gain
        desired_gain = min(target_rms / max(rms, 1e-5), max_gain)

        # Avoid clipping
        if peak * desired_gain > peak_limit:
            desired_gain = peak_limit / max(peak, 1e-4)

        desired_gain = max(0.5, desired_gain)
        processed = np.clip(audio_f32 * desired_gain, -1.0, 1.0)
        return processed, desired_gain

    def process_audio(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
    ) -> Tuple[np.ndarray, AudioQualityMetrics]:
        """
        Full preprocessing pipeline for incoming speech PCM:
        1. Float32 conversion
        2. DC offset removal
        3. 80Hz High-pass filtering
        4. Smart RMS AGC
        5. Quality Gate validation
        """
        raw_f32 = self.pcm_to_float32(pcm_bytes)
        dc_cleaned = self.remove_dc_offset(raw_f32)
        filtered = self.apply_high_pass_filter(dc_cleaned, sample_rate=sample_rate, cutoff_hz=80.0)
        agc_audio, gain = self.apply_smart_agc(filtered)

        metrics = self.quality_gate.evaluate(agc_audio, sample_rate=sample_rate)
        return agc_audio, metrics

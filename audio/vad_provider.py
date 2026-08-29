"""
VAD Provider Abstraction Layer for Jarvis:
Provides Silero VAD (PyTorch / ONNX) and Adaptive Energy VAD fallback
with continuous listening, rolling pre-buffer, and hysteresis boundary detection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
import logging
import os
from typing import Any, Tuple
import numpy as np

log = logging.getLogger("vad_provider")


class VADProvider(ABC):
    """Abstract Base Class for Voice Activity Detection Providers."""

    @abstractmethod
    def feed(self, chunk: np.ndarray, is_speech_flag: bool | None = None) -> Tuple[str, bytes | None]:
        """
        Feed an audio chunk (float32, 16kHz mono).
        Returns:
            (event_name, pcm_bytes)
            event_name: "SILENCE" | "SPEECH_START" | "SPEAKING" | "SPEECH_END"
            pcm_bytes: Populated with full utterance PCM bytes on "SPEECH_END", None otherwise.
        """
        pass

    @abstractmethod
    def is_speech(self, chunk: np.ndarray) -> bool:
        """Returns True if the current frame contains active speech."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state machine buffers."""
        pass


class SileroVADProvider(VADProvider):
    """
    High-accuracy Neural Voice Activity Detector powered by Silero VAD.
    Runs via ONNX Runtime or PyTorch for low-latency speech boundary detection.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        speech_start_chunks: int = 2,    # ~160ms speech confirmation
        end_silence_ms: int = 650,       # 650ms continuous silence for natural conversational turn detection
        max_utterance_s: float = 12.0,
        pre_roll_chunks: int = 4,        # ~320ms pre-buffer
    ):
        self.sample_rate = sample_rate
        self.threshold = float(os.environ.get("SILERO_VAD_THRESHOLD", str(threshold)))
        self.speech_start_chunks = int(os.environ.get("VAD_SPEECH_START_CHUNKS", str(speech_start_chunks)))
        
        cfg_end_silence = int(os.environ.get("VAD_HANGOVER_MS", os.environ.get("VAD_END_SILENCE_MS", str(end_silence_ms))))
        self.end_silence_chunks = max(3, int(cfg_end_silence / 80))
        
        self.max_utterance_chunks = int(max_utterance_s * 1000 / 80)
        
        cfg_pre_roll_ms = int(os.environ.get("VAD_PRE_ROLL_MS", str(pre_roll_chunks * 80)))
        actual_pre_roll_chunks = max(2, int(cfg_pre_roll_ms / 80))
        self.pre_roll = deque(maxlen=actual_pre_roll_chunks)

        self.state = "SILENCE"  # "SILENCE" | "SPEAKING"
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.utterance_chunks: list[bytes] = []

        self._model: Any = None
        self._init_model()

    def _init_model(self) -> None:
        """Initialize Silero VAD using PyTorch hub or ONNX Runtime."""
        try:
            import torch
            # Check local torch cache first
            hub_dir = torch.hub.get_dir()
            silero_dir = os.path.join(hub_dir, "snakers4_silero-vad_master")
            if os.path.isdir(silero_dir):
                log.info("[VAD] Loading Silero VAD from local torch hub cache: %s", silero_dir)
                model, _ = torch.hub.load(
                    repo_or_dir=silero_dir,
                    model="silero_vad",
                    source="local",
                    trust_repo=True,
                )
            else:
                log.info("[VAD] Loading Silero VAD model via torch.hub...")
                model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False,
                    trust_repo=True,
                )
            self._model = model
            self._model.eval()
            log.info("[VAD] Silero VAD neural model ready (threshold=%.2f).", self.threshold)
        except Exception as e:
            log.warning("[VAD] Silero VAD model init note (%s). Using adaptive Energy VAD fallback.", e)
            self._model = None

    def is_speech(self, chunk: np.ndarray) -> bool:
        """Compute speech probability for audio frame."""
        if chunk is None or chunk.size == 0:
            return False

        if self._model is not None:
            try:
                import torch
                tensor = torch.from_numpy(chunk.flatten()).float()
                if tensor.abs().max() > 1.0:
                    tensor = tensor / 32768.0
                prob = self._model(tensor, self.sample_rate).item()
                return prob >= self.threshold
            except Exception as e:
                log.debug("[VAD] Silero inference error: %s", e)

        # Fallback to RMS calculation if neural model unavailable
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        return rms >= 0.015

    def feed(self, chunk: np.ndarray, is_speech_flag: bool | None = None) -> Tuple[str, bytes | None]:
        pcm_bytes = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        speech_detected = is_speech_flag if is_speech_flag is not None else self.is_speech(chunk)

        if self.state == "SILENCE":
            self.pre_roll.append(pcm_bytes)
            if speech_detected:
                self.consecutive_speech += 1
                if self.consecutive_speech >= self.speech_start_chunks:
                    self.state = "SPEAKING"
                    self.consecutive_silence = 0
                    self.utterance_chunks = list(self.pre_roll)
                    log.info("[VAD] Speech started.")
                    return "SPEECH_START", None
            else:
                self.consecutive_speech = 0
            return "SILENCE", None

        elif self.state == "SPEAKING":
            self.utterance_chunks.append(pcm_bytes)
            if speech_detected:
                self.consecutive_silence = 0
            else:
                self.consecutive_silence += 1

            if (
                self.consecutive_silence >= self.end_silence_chunks
                or len(self.utterance_chunks) >= self.max_utterance_chunks
            ):
                self.state = "SILENCE"
                self.consecutive_speech = 0
                self.consecutive_silence = 0
                full_pcm = b"".join(self.utterance_chunks)
                self.utterance_chunks = []
                log.info("[VAD] Speech ended (utterance bytes=%d).", len(full_pcm))
                return "SPEECH_END", full_pcm

            return "SPEAKING", None

        return "SILENCE", None

    def reset(self) -> None:
        self.state = "SILENCE"
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.utterance_chunks = []
        if self._model is not None and hasattr(self._model, "reset_states"):
            try:
                self._model.reset_states()
            except Exception:
                pass


class EnergyVADProvider(VADProvider):
    """
    Adaptive Energy VAD provider with rolling pre-buffer and silence tolerance.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        pre_roll_chunks: int = 4,
        speech_start_chunks: int = 2,
        end_silence_ms: int = 380,
        max_utterance_s: float = 10.0,
    ):
        self.sample_rate = sample_rate
        self.pre_roll = deque(maxlen=pre_roll_chunks)
        self.speech_start_chunks = speech_start_chunks
        self.end_silence_chunks = max(3, int(end_silence_ms / 80))
        self.max_utterance_chunks = int(max_utterance_s * 1000 / 80)

        self.state = "SILENCE"
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.utterance_chunks: list[bytes] = []

    def is_speech(self, chunk: np.ndarray) -> bool:
        if chunk is None or chunk.size == 0:
            return False
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        return rms >= 0.015

    def feed(self, chunk: np.ndarray, is_speech_flag: bool | None = None) -> Tuple[str, bytes | None]:
        pcm_bytes = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        is_speech = is_speech_flag if is_speech_flag is not None else self.is_speech(chunk)

        if self.state == "SILENCE":
            self.pre_roll.append(pcm_bytes)
            if is_speech:
                self.consecutive_speech += 1
                if self.consecutive_speech >= self.speech_start_chunks:
                    self.state = "SPEAKING"
                    self.consecutive_silence = 0
                    self.utterance_chunks = list(self.pre_roll)
                    return "SPEECH_START", None
            else:
                self.consecutive_speech = 0
            return "SILENCE", None

        elif self.state == "SPEAKING":
            self.utterance_chunks.append(pcm_bytes)
            if is_speech:
                self.consecutive_silence = 0
            else:
                self.consecutive_silence += 1

            if (
                self.consecutive_silence >= self.end_silence_chunks
                or len(self.utterance_chunks) >= self.max_utterance_chunks
            ):
                self.state = "SILENCE"
                self.consecutive_speech = 0
                self.consecutive_silence = 0
                full_pcm = b"".join(self.utterance_chunks)
                self.utterance_chunks = []
                return "SPEECH_END", full_pcm

            return "SPEAKING", None

        return "SILENCE", None

    def reset(self) -> None:
        self.state = "SILENCE"
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.utterance_chunks = []


def get_vad_provider(name: str | None = None, sample_rate: int = 16000) -> VADProvider:
    """Factory helper to obtain configured VADProvider."""
    provider_name = (name or os.environ.get("VAD_PROVIDER", "silero")).strip().lower()
    if provider_name in ("silero", "silero_vad", "neural"):
        return SileroVADProvider(sample_rate=sample_rate)
    elif provider_name in ("energy", "rms", "heuristic"):
        return EnergyVADProvider(sample_rate=sample_rate)
    return SileroVADProvider(sample_rate=sample_rate)


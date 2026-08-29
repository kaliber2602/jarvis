"""
Voice Activity Detection (VAD) with rolling pre-buffer,
adaptive energy thresholding, Silero neural VAD, and continuous speech boundary detection.
"""

from __future__ import annotations

import logging
import os
import numpy as np

from .vad_provider import EnergyVADProvider, SileroVADProvider, VADProvider

log = logging.getLogger("vad")


class AudioVAD:
    """
    Backward-compatible Voice Activity Detector (VAD) adapter.
    Delegates to configured VAD provider (SileroVADProvider or EnergyVADProvider).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        pre_roll_chunks: int = 6,      # ~480ms rolling pre-buffer at 80ms/chunk
        speech_start_chunks: int = 2,  # ~160ms speech confirmation
        end_silence_ms: int = 650,     # 650ms continuous silence for natural conversational turn detection
        max_utterance_s: float = 12.0,
        provider_name: str | None = None,
    ):
        self.sample_rate = sample_rate
        prov = provider_name or os.environ.get("VAD_PROVIDER", "silero").strip().lower()
        self.provider_name = prov

        if prov == "silero":
            self._provider: VADProvider = SileroVADProvider(
                sample_rate=sample_rate,
                speech_start_chunks=speech_start_chunks,
                end_silence_ms=end_silence_ms,
                max_utterance_s=max_utterance_s,
                pre_roll_chunks=pre_roll_chunks,
            )
        else:
            self._provider = EnergyVADProvider(
                sample_rate=sample_rate,
                pre_roll_chunks=pre_roll_chunks,
                speech_start_chunks=speech_start_chunks,
                end_silence_ms=end_silence_ms,
                max_utterance_s=max_utterance_s,
            )

    @property
    def state(self) -> str:
        if hasattr(self._provider, "state"):
            return self._provider.state
        return "SILENCE"

    def is_speech(self, chunk: np.ndarray) -> bool:
        return self._provider.is_speech(chunk)

    def feed(self, chunk: np.ndarray, is_speech: bool | None = None) -> tuple[str, bytes | None]:
        """
        Feed an audio frame to the VAD.
        Returns:
            (event_name, pcm_bytes)
            event_name can be "SILENCE", "SPEECH_START", "SPEAKING", "SPEECH_END".
            pcm_bytes is populated when event_name is "SPEECH_END".
        """
        return self._provider.feed(chunk, is_speech_flag=is_speech)

    def reset(self) -> None:
        """Reset the VAD state machine and clear all utterance buffers."""
        self._provider.reset()

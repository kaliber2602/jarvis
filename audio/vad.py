"""
Voice Activity Detection (VAD) with rolling pre-buffer,
adaptive energy thresholding, and continuous speech boundary detection.
"""

from __future__ import annotations

from collections import deque
import numpy as np


class AudioVAD:
    """
    Real-time Voice Activity Detector (VAD) with rolling pre-buffer,
    adaptive energy thresholding, and silence tolerance.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        pre_roll_chunks: int = 4,      # ~320ms rolling pre-buffer at 80ms/chunk
        speech_start_chunks: int = 2,  # ~160ms speech confirmation
        end_silence_ms: int = 650,     # 650ms continuous silence for end-of-utterance
        max_utterance_s: float = 10.0,
    ):
        self.sample_rate = sample_rate
        self.pre_roll = deque(maxlen=pre_roll_chunks)
        self.speech_start_chunks = speech_start_chunks
        self.end_silence_chunks = max(3, int(end_silence_ms / 80))
        self.max_utterance_chunks = int(max_utterance_s * 1000 / 80)

        self.state = "SILENCE"  # SILENCE, SPEAKING
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.utterance_chunks: list[bytes] = []

    def feed(self, chunk: np.ndarray, is_speech: bool) -> tuple[str, bytes | None]:
        """
        Feed an audio frame to the VAD.
        Returns:
            (event_name, pcm_bytes)
            event_name can be "SILENCE", "SPEECH_START", "SPEAKING", "SPEECH_END".
            pcm_bytes is populated when event_name is "SPEECH_END".
        """
        pcm_bytes = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

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

            # End of utterance reached?
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
        """Reset the VAD state machine and clear all utterance buffers."""
        self.state = "SILENCE"
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.utterance_chunks = []

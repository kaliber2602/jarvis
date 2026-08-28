"""
SoundDevice Audio Playback Engine for Jarvis:
Provides non-blocking audio playback, real-time RMS visual telemetry to UI Orb,
and instant speech barge-in interruption.
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from typing import Callable, Optional
import wave
import numpy as np
import sounddevice as sd

from runtime_bridge import JarvisBridge

log = logging.getLogger("playback")


class SoundDevicePlayback:
    """
    Thread-safe Non-blocking Audio Playback Engine.
    Streams live amplitude to the UI Orb and supports instantaneous barge-in cancellation.
    """

    _instance: SoundDevicePlayback | None = None

    @classmethod
    def get_instance(cls) -> SoundDevicePlayback:
        if cls._instance is None:
            cls._instance = SoundDevicePlayback()
        return cls._instance

    def __init__(self, chunk_ms: int = 40):
        self.chunk_ms = chunk_ms
        self._lock = threading.RLock()
        self._is_playing = False
        self._is_paused = False
        self._stop_requested = threading.Event()
        self._playback_thread: Optional[threading.Thread] = None
        self._bridge = JarvisBridge.get_instance()

    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    def play_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 24000,
        on_done: Optional[Callable[[], None]] = None,
    ) -> bool:
        """
        Start non-blocking playback of 16-bit Mono PCM bytes.
        """
        if not pcm_bytes:
            if on_done:
                on_done()
            return False

        self.stop()  # Stop any previous playback immediately

        with self._lock:
            self._is_playing = True
            self._is_paused = False
            self._stop_requested.clear()

        def _worker():
            try:
                pcm_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
                pcm_f = pcm_i16.astype(np.float32) / 32768.0

                chunk_size = max(1, int(sample_rate * self.chunk_ms / 1000))
                total_samples = len(pcm_f)

                self._bridge.set_state("speaking")
                log.info("[PLAYBACK] Playing %d samples (%.2fs at %d Hz)...", total_samples, total_samples / sample_rate, sample_rate)

                # Open sounddevice OutputStream for smooth chunked streaming and instant cancellation
                with sd.OutputStream(samplerate=sample_rate, channels=1, dtype="float32") as stream:
                    idx = 0
                    start_time = time.monotonic()

                    while idx < total_samples and not self._stop_requested.is_set():
                        while self._is_paused and not self._stop_requested.is_set():
                            time.sleep(0.05)

                        end_idx = min(idx + chunk_size, total_samples)
                        chunk = pcm_f[idx:end_idx]

                        if chunk.size > 0:
                            # Stream audio buffer to output device
                            stream.write(chunk)

                            # Calculate and emit live RMS amplitude to UI Orb
                            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                            self._bridge.emit_tts_level(min(1.0, rms * 3.8))

                        idx = end_idx

                        # Timing regulation
                        elapsed = time.monotonic() - start_time
                        expected = idx / float(sample_rate)
                        if expected > elapsed:
                            time.sleep(expected - elapsed)

                if self._stop_requested.is_set():
                    log.info("[PLAYBACK] 🛑 Playback stopped early by barge-in interruption.")
                else:
                    log.info("[PLAYBACK] Playback completed normally.")

            except Exception as e:
                log.error("[PLAYBACK] Error during audio playback: %s", e, exc_info=True)
            finally:
                with self._lock:
                    self._is_playing = False
                if self._bridge.is_conversation_active():
                    self._bridge.set_state("listening")
                if on_done and not self._stop_requested.is_set():
                    try:
                        on_done()
                    except Exception as e:
                        log.debug("on_done callback error: %s", e)

        self._playback_thread = threading.Thread(target=_worker, name="JarvisPlaybackWorker", daemon=True)
        self._playback_thread.start()
        return True

    def play_wav_file(
        self,
        wav_path: str | Path,
        on_done: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Play a WAV file non-blockingly."""
        p = Path(wav_path)
        if not p.is_file():
            log.warning("[PLAYBACK] File not found: %s", p)
            return False

        try:
            with wave.open(str(p), "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                raw_bytes = wf.readframes(wf.getnframes())

                if channels != 1 or sample_width != 2:
                    log.warning("[PLAYBACK] Converting WAV (%d ch, %d byte/s) to 16-bit mono...", channels, sample_width)

            return self.play_pcm(raw_bytes, sample_rate=framerate, on_done=on_done)
        except Exception as e:
            log.error("[PLAYBACK] Could not read WAV file %s: %s", p, e)
            return False

    def stop(self) -> None:
        """Instantly stop active audio playback (Barge-in)."""
        with self._lock:
            if not self._is_playing:
                return
            log.info("[PLAYBACK] Stop signal received.")
            self._stop_requested.set()

        try:
            sd.stop()
        except Exception:
            pass

        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.2)

        with self._lock:
            self._is_playing = False

    def pause(self) -> None:
        with self._lock:
            self._is_paused = True

    def resume(self) -> None:
        with self._lock:
            self._is_paused = False

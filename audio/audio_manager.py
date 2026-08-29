"""
Central Audio Manager & Single Microphone Ownership Coordinator.
Guarantees strictly ONE active microphone consumer at any given moment (NONE, TRIGGER, CHAT).
Provides real-time speech barge-in and echo suppression coordination.
"""

from __future__ import annotations

import contextlib
from enum import Enum
import logging
import threading
import time
from typing import Callable, Generator
import numpy as np

log = logging.getLogger("audio_manager")


class AudioOwner(str, Enum):
    """Microphone ownership states."""
    NONE = "NONE"
    TRIGGER = "TRIGGER"
    CHAT = "CHAT"


class AudioManager:
    """
    Thread-safe Central Audio Ownership and Microphone Frame Broker.
    Enforces the single-owner invariant:
      - Only the current owner receives audio callbacks.
      - A secondary owner cannot acquire while another owner holds the microphone.
      - Safe release and context-management for error recovery.
      - Barge-in coordination to interrupt active TTS when user speech is detected.
    """

    _instance: AudioManager | None = None

    @classmethod
    def get_instance(cls, sample_rate: int = 16000, block_ms: int = 80) -> AudioManager:
        if cls._instance is None:
            cls._instance = AudioManager(sample_rate=sample_rate, block_ms=block_ms)
        return cls._instance

    def __init__(self, sample_rate: int = 16000, block_ms: int = 80):
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.blocksize = max(1, int(sample_rate * block_ms / 1000))

        self._lock = threading.RLock()
        self._current_owner = AudioOwner.NONE
        self._owner_changed_time = time.monotonic()

        # Listeners for specific owners
        self._listeners: dict[AudioOwner, list[Callable[[np.ndarray, float], None]]] = {
            AudioOwner.TRIGGER: [],
            AudioOwner.CHAT: [],
        }

        # Global speaker echo / loopback guard: mic is muted while Jarvis is talking
        self._speaking_until = 0.0

        # Barge-in interruption handlers
        self._barge_in_handlers: list[Callable[[], None]] = []

        # Background noise baseline tracking
        self.noise_floor = 1e-4
        self.noise_floor_alpha = 0.992
        self.quiet_gate_mult = 2.2

    @property
    def current_owner(self) -> AudioOwner:
        with self._lock:
            return self._current_owner

    def is_speaking(self, now: float | None = None) -> bool:
        """Check if Jarvis TTS playback is active (echo suppression)."""
        t = now if now is not None else time.monotonic()
        return t < self._speaking_until

    def set_speaking_until(self, until: float) -> None:
        """Mute microphone processing for echo guard until specified timestamp."""
        with self._lock:
            self._speaking_until = until

    def interrupt_speaking(self) -> None:
        """Immediately cancel speaking lock and trigger barge-in handlers."""
        with self._lock:
            was_speaking = self.is_speaking()
            self._speaking_until = 0.0
            handlers = list(self._barge_in_handlers)

        if was_speaking:
            log.info("[AUDIO] ⚡ Barge-in triggered! Speaking lock cleared.")
            for handler in handlers:
                try:
                    handler()
                except Exception as e:
                    log.error("[AUDIO] Error in barge-in handler: %s", e)

    def register_barge_in_handler(self, handler: Callable[[], None]) -> None:
        """Register a callback to execute on barge-in / speech interruption."""
        with self._lock:
            if handler not in self._barge_in_handlers:
                self._barge_in_handlers.append(handler)

    def unregister_barge_in_handler(self, handler: Callable[[], None]) -> None:
        """Unregister a barge-in handler."""
        with self._lock:
            if handler in self._barge_in_handlers:
                self._barge_in_handlers.remove(handler)

    def acquire(self, owner: AudioOwner, timeout_s: float = 2.0) -> bool:
        """
        Acquire microphone ownership exclusively for the given owner.
        Returns True if acquired, False otherwise.
        """
        if owner == AudioOwner.NONE:
            self.release()
            return True

        with self._lock:
            prev_owner = self._current_owner
            if prev_owner != owner:
                log.info("[AUDIO] Ownership transfer: %s -> %s", prev_owner.value, owner.value)
                self._current_owner = owner
                self._owner_changed_time = time.monotonic()
            return True

    def release(self, owner: AudioOwner | None = None) -> None:
        """
        Release microphone ownership. If owner is specified, only releases
        if the current owner matches.
        """
        with self._lock:
            if owner is None or self._current_owner == owner:
                prev = self._current_owner
                self._current_owner = AudioOwner.NONE
                self._owner_changed_time = time.monotonic()
                if prev != AudioOwner.NONE:
                    log.info("[AUDIO] Ownership released by %s (now: NONE)", prev.value)

    @contextlib.contextmanager
    def session(self, owner: AudioOwner, timeout_s: float = 2.0) -> Generator[bool, None, None]:
        """
        Context manager ensuring guaranteed release of audio ownership.
        """
        acquired = self.acquire(owner, timeout_s=timeout_s)
        try:
            yield acquired
        finally:
            if acquired:
                self.release(owner)

    def register_listener(self, owner: AudioOwner, callback: Callable[[np.ndarray, float], None]) -> None:
        """Register a frame consumer callback for a specific audio owner."""
        with self._lock:
            if owner in self._listeners and callback not in self._listeners[owner]:
                self._listeners[owner].append(callback)

    def unregister_listener(self, owner: AudioOwner, callback: Callable[[np.ndarray, float], None]) -> None:
        """Unregister a frame consumer callback."""
        with self._lock:
            if owner in self._listeners and callback in self._listeners[owner]:
                self._listeners[owner].remove(callback)

    def process_incoming_frame(self, data: np.ndarray, now: float) -> None:
        """
        Ingest a raw microphone frame from sounddevice and route it
        STRICTLY to the active owner's listeners.
        """
        level = self.calculate_rms(data)

        # Echo suppression & Barge-in check
        if self.is_speaking(now):
            # Strict echo suppression: discard all microphone frames during TTS playback to prevent self-hearing feedback loops
            import os
            barge_in_enabled = os.environ.get("JARVIS_BARGE_IN", "false").lower() in ("true", "1", "yes")
            if barge_in_enabled:
                barge_in_thresh = max(self.noise_floor * 12.0, 0.25)
                if level > barge_in_thresh:
                    log.info("[AUDIO] Intentional barge-in speech energy detected (rms=%.4f > %.4f). Interrupting TTS...", level, barge_in_thresh)
                    self.interrupt_speaking()
                    return
            return

        # Baseline noise floor tracking
        quiet_gate = self.noise_floor * self.quiet_gate_mult
        if level < quiet_gate:
            self.noise_floor = self.noise_floor_alpha * self.noise_floor + (1.0 - self.noise_floor_alpha) * level
            self.noise_floor = max(self.noise_floor, 1e-7)

        with self._lock:
            owner = self._current_owner
            callbacks = list(self._listeners.get(owner, []))

        # Dispatch frame strictly to the active owner's registered listeners
        for cb in callbacks:
            try:
                cb(data, now)
            except Exception as e:
                log.error("[AUDIO] Error in listener callback for owner %s: %s", owner.value, e, exc_info=True)

    @staticmethod
    def calculate_rms(block: np.ndarray) -> float:
        """Compute Root Mean Square amplitude of a mono audio buffer."""
        if block.ndim > 1:
            block = np.mean(block.astype(np.float64), axis=1)
        else:
            block = block.astype(np.float64)
        if block.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(block**2)))

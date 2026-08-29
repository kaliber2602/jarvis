"""
Unit tests for AudioManager and AudioOwner single-ownership invariant.
"""

import os
import sys
import threading
import time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio.audio_manager import AudioManager, AudioOwner
from audio.vad import AudioVAD


def test_audio_manager_single_ownership():
    mgr = AudioManager(sample_rate=16000, block_ms=80)
    mgr.release()  # Reset
    assert mgr.current_owner == AudioOwner.NONE

    # Acquire TRIGGER
    assert mgr.acquire(AudioOwner.TRIGGER) is True
    assert mgr.current_owner == AudioOwner.TRIGGER

    # Frame dispatch to TRIGGER listener
    received_trigger = []
    received_chat = []

    def trigger_cb(frame, now):
        received_trigger.append((frame, now))

    def chat_cb(frame, now):
        received_chat.append((frame, now))

    mgr.register_listener(AudioOwner.TRIGGER, trigger_cb)
    mgr.register_listener(AudioOwner.CHAT, chat_cb)

    dummy_frame = np.zeros(1280, dtype=np.float32)
    mgr.process_incoming_frame(dummy_frame, time.monotonic())

    assert len(received_trigger) == 1
    assert len(received_chat) == 0

    # CHAT preempts TRIGGER
    assert mgr.acquire(AudioOwner.CHAT) is True
    assert mgr.current_owner == AudioOwner.CHAT

    mgr.process_incoming_frame(dummy_frame, time.monotonic())
    assert len(received_trigger) == 1  # Trigger did not receive new frame
    assert len(received_chat) == 1     # Chat received the new frame

    # Release CHAT
    mgr.release(AudioOwner.CHAT)
    assert mgr.current_owner == AudioOwner.NONE

    mgr.process_incoming_frame(dummy_frame, time.monotonic())
    assert len(received_trigger) == 1
    assert len(received_chat) == 1


def test_audio_manager_session_context():
    mgr = AudioManager(sample_rate=16000, block_ms=80)
    mgr.release()

    with mgr.session(AudioOwner.CHAT) as acquired:
        assert acquired is True
        assert mgr.current_owner == AudioOwner.CHAT

    # Must be automatically released
    assert mgr.current_owner == AudioOwner.NONE


def test_vad_state_machine():
    vad = AudioVAD(sample_rate=16000)
    silent_frame = np.zeros(1280, dtype=np.float32)
    speech_frame = np.ones(1280, dtype=np.float32) * 0.5

    # Feed silence
    evt, pcm = vad.feed(silent_frame, is_speech=False)
    assert evt == "SILENCE"
    assert pcm is None

    # Feed speech confirmation
    evt, pcm = vad.feed(speech_frame, is_speech=True)
    evt, pcm = vad.feed(speech_frame, is_speech=True)
    assert evt == "SPEECH_START"
    assert pcm is None

    # Feed ongoing speech
    evt, pcm = vad.feed(speech_frame, is_speech=True)
    assert evt == "SPEAKING"

    # Feed silence until end of utterance
    end_detected = False
    for _ in range(10):
        evt, pcm = vad.feed(silent_frame, is_speech=False)
        if evt == "SPEECH_END":
            end_detected = True
            break

    assert end_detected
    assert pcm is not None
    assert len(pcm) > 0


if __name__ == "__main__":
    test_audio_manager_single_ownership()
    test_audio_manager_session_context()
    test_vad_state_machine()
    print("All audio ownership & VAD tests passed!")

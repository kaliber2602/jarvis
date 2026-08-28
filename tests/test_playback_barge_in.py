from __future__ import annotations

from pathlib import Path
import sys
import time

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio.audio_manager import AudioManager, AudioOwner
from audio.playback import SoundDevicePlayback


def test_playback_instance():
    pb = SoundDevicePlayback.get_instance()
    assert pb is not None
    assert not pb.is_playing()


def test_playback_empty():
    pb = SoundDevicePlayback.get_instance()
    called = []
    res = pb.play_pcm(b"", on_done=lambda: called.append(True))
    assert res is False
    assert called == [True]


def test_barge_in_interruption():
    pb = SoundDevicePlayback.get_instance()
    # 0.5s of silence PCM
    sample_rate = 16000
    pcm_dummy = b"\x00\x00" * int(sample_rate * 0.5)

    pb.play_pcm(pcm_dummy, sample_rate=sample_rate)
    time.sleep(0.05)
    # Trigger barge in stop
    pb.stop()
    assert not pb.is_playing()


def test_audio_manager_barge_in_handler():
    mgr = AudioManager.get_instance()
    barge_in_fired = []

    mgr.register_barge_in_handler(lambda: barge_in_fired.append(True))
    mgr.set_speaking_until(time.monotonic() + 5.0)
    assert mgr.is_speaking()

    # Interrupt speaking
    mgr.interrupt_speaking()
    assert not mgr.is_speaking()
    assert len(barge_in_fired) >= 1


if __name__ == "__main__":
    test_playback_instance()
    test_playback_empty()
    test_barge_in_interruption()
    test_audio_manager_barge_in_handler()
    print("All Playback & Barge-In Interruption tests passed successfully!")

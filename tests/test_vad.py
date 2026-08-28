from __future__ import annotations

from pathlib import Path
import sys
import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio.vad import AudioVAD
from audio.vad_provider import EnergyVADProvider, SileroVADProvider, get_vad_provider


def test_energy_vad_provider():
    vad = EnergyVADProvider(sample_rate=16000)
    silence = np.zeros(512, dtype=np.float32)
    speech = np.random.uniform(-0.5, 0.5, 512).astype(np.float32)

    # Silence frame
    evt, pcm = vad.feed(silence, is_speech_flag=False)
    assert evt == "SILENCE"
    assert pcm is None

    # Speech frame
    evt, pcm = vad.feed(speech, is_speech_flag=True)
    assert evt in ("SPEECH_START", "SPEAKING", "SILENCE")


def test_silero_vad_provider():
    vad = SileroVADProvider(sample_rate=16000)
    silence = np.zeros(512, dtype=np.float32)
    evt, pcm = vad.feed(silence)
    assert evt in ("SILENCE", "SPEECH_START")


def test_audio_vad_adapter():
    adapter = AudioVAD(sample_rate=16000)
    silence = np.zeros(512, dtype=np.float32)
    evt, pcm = adapter.feed(silence, is_speech=False)
    assert evt in ("SILENCE", "SPEECH_START")


def test_get_vad_provider():
    silero = get_vad_provider("silero")
    assert isinstance(silero, SileroVADProvider)

    energy = get_vad_provider("energy")
    assert isinstance(energy, EnergyVADProvider)


if __name__ == "__main__":
    test_energy_vad_provider()
    test_silero_vad_provider()
    test_audio_vad_adapter()
    test_get_vad_provider()
    print("All VAD Provider unit tests passed successfully!")

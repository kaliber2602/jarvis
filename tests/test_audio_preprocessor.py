from __future__ import annotations

import sys
from pathlib import Path
import unittest
import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio.audio_preprocessor import AudioPreprocessor, AudioQualityGate, AudioQualityMetrics


class TestAudioPreprocessor(unittest.TestCase):
    """Test suite for AudioPreprocessor and AudioQualityGate."""

    def setUp(self):
        self.preprocessor = AudioPreprocessor.get_instance()
        self.quality_gate = AudioQualityGate.get_instance()
        self.sample_rate = 16000

    def test_quality_gate_empty_input(self):
        metrics = self.quality_gate.evaluate(np.zeros(0, dtype=np.float32), sample_rate=self.sample_rate)
        self.assertFalse(metrics.is_valid)
        self.assertEqual(metrics.rejection_reason, "empty_buffer")

    def test_quality_gate_too_short(self):
        # 0.15s short burst (e.g. mic click)
        short_audio = (np.random.randn(int(self.sample_rate * 0.15)) * 0.05).astype(np.float32)
        metrics = self.quality_gate.evaluate(short_audio, sample_rate=self.sample_rate)
        self.assertFalse(metrics.is_valid)
        self.assertIn("too_short", metrics.rejection_reason)

    def test_quality_gate_insufficient_energy(self):
        # 1.0s of pure silence / low hum (RMS ~ 0.0001)
        silent_audio = np.full(self.sample_rate, 0.0001, dtype=np.float32)
        metrics = self.quality_gate.evaluate(silent_audio, sample_rate=self.sample_rate)
        self.assertFalse(metrics.is_valid)
        self.assertIn("insufficient_energy", metrics.rejection_reason)

    def test_quality_gate_valid_speech(self):
        # 1.5s simulated speech signal with good RMS (~0.05)
        t = np.linspace(0, 1.5, int(self.sample_rate * 1.5), endpoint=False)
        speech_signal = (0.20 * np.sin(2 * np.pi * 300 * t) + 0.10 * np.sin(2 * np.pi * 1200 * t)).astype(np.float32)
        metrics = self.quality_gate.evaluate(speech_signal, sample_rate=self.sample_rate)
        self.assertTrue(metrics.is_valid)
        self.assertIsNone(metrics.rejection_reason)
        self.assertGreater(metrics.rms, 0.01)

    def test_dc_offset_removal(self):
        audio = (np.sin(np.linspace(0, 10, 1600)) + 0.35).astype(np.float32)
        cleaned = self.preprocessor.remove_dc_offset(audio)
        self.assertAlmostEqual(float(np.mean(cleaned)), 0.0, places=4)

    def test_smart_agc_gain_ceiling(self):
        # Quiet signal (RMS ~ 0.005)
        quiet_signal = (np.sin(np.linspace(0, 20, 16000)) * 0.007).astype(np.float32)
        agc_audio, gain = self.preprocessor.apply_smart_agc(quiet_signal, target_rms=0.09, max_gain=10.0)
        self.assertGreater(gain, 1.0)
        self.assertLessEqual(gain, 10.0)
        self.assertLessEqual(float(np.max(np.abs(agc_audio))), 0.95)

    def test_high_pass_filter_attenuates_low_freq(self):
        # 30Hz low frequency rumble
        t = np.linspace(0, 1.0, self.sample_rate, endpoint=False)
        rumble = np.sin(2 * np.pi * 30 * t).astype(np.float32)
        filtered = self.preprocessor.apply_high_pass_filter(rumble, sample_rate=self.sample_rate, cutoff_hz=80.0)
        # Filtered 30Hz signal should have significantly lower RMS than input
        rms_in = np.sqrt(np.mean(rumble**2))
        rms_out = np.sqrt(np.mean(filtered**2))
        self.assertLess(rms_out, rms_in * 0.70)


if __name__ == "__main__":
    unittest.main()

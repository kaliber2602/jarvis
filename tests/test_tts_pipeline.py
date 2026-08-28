from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import wave

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio.tts.voice_dataset import VoiceDataset, VoiceDatasetMetadata
from audio.tts.voice_profile import VoiceProfile, get_default_jarvis_profile
from audio.tts.voice_asset_generator import PREDEFINED_VOICE_SCRIPTS, VoiceAssetGenerator
from audio.tts.tts_provider import SystemTTSProvider, HybridTTSProvider, get_tts_provider


def create_dummy_wav(path: Path, duration_s: float = 0.2, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_s * sample_rate)
    dummy_bytes = b"\x00\x00" * num_samples
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(dummy_bytes)


def test_voice_dataset():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dataset = VoiceDataset(tmp_dir)
        assert dataset.get_sample_count() == 0
        assert dataset.get_missing_sample_count(20) == 20
        assert not dataset.is_ready(min_samples=1)

        # Add dummy sample
        sample_file = Path(tmp_dir) / "sample_001.wav"
        create_dummy_wav(sample_file)

        assert dataset.get_sample_count() == 1
        assert dataset.get_missing_sample_count(20) == 19
        assert dataset.is_ready(min_samples=1)
        assert dataset.validate_sample_wav(sample_file)

        # Metadata save & load
        dataset.save_metadata(voice_id="test-voice", sample_count=1)
        meta = dataset.load_metadata()
        assert meta is not None
        assert meta.voice_id == "test-voice"
        assert meta.sample_count == 1
        assert dataset.get_reference_audio() == str(sample_file)


def test_voice_profile():
    with tempfile.TemporaryDirectory() as tmp_dir:
        prof = VoiceProfile(
            id="test-profile",
            name="Test Jarvis",
            languages=["en", "vi"],
            provider="vieneu",
            sample_count=20,
        )
        saved_file = prof.save_to_dir(tmp_dir)
        assert saved_file.is_file()

        loaded = VoiceProfile.load_from_dir(tmp_dir)
        assert loaded is not None
        assert loaded.id == "test-profile"
        assert loaded.name == "Test Jarvis"
        assert "en" in loaded.languages

        default_p = get_default_jarvis_profile()
        assert default_p.id == "jarvis-default"


def test_voice_asset_generator():
    assert len(PREDEFINED_VOICE_SCRIPTS) >= 15
    with tempfile.TemporaryDirectory() as tmp_dir:
        dataset = VoiceDataset(tmp_dir)
        gen = VoiceAssetGenerator(api_key="", voice_id="")
        # When api_key is missing, bootstrap should return 0 safely without crashing
        generated = gen.bootstrap_dataset(dataset, target_sample_count=5)
        assert generated == 0


def test_tts_providers():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dataset = VoiceDataset(tmp_dir)
        create_dummy_wav(Path(tmp_dir) / "sample_001.wav")

        hybrid = HybridTTSProvider(dataset_path=tmp_dir, target_sample_count=1)
        assert hybrid is not None

        # System SAPI Provider
        sys_tts = SystemTTSProvider()
        pcm, rate = sys_tts.synthesize("")
        assert pcm == b""


if __name__ == "__main__":
    test_voice_dataset()
    test_voice_profile()
    test_voice_asset_generator()
    test_tts_providers()
    print("All Voice Dataset, Profile, Asset Generator & TTS Provider tests passed successfully!")

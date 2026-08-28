"""
Voice Dataset Management for Jarvis:
Manages local WAV audio voice datasets, formats, metadata.json,
and provides reference audio for VieNeu-TTS voice cloning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional
import wave

log = logging.getLogger("voice_dataset")


@dataclass
class VoiceDatasetMetadata:
    voice_id: str
    provider: str = "elevenlabs"
    sample_count: int = 0
    language: str = "en"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    audio_format: str = "wav"
    sample_rate: int = 24000
    description: str = "Jarvis Voice Dataset for VieNeu-TTS local cloning"

    def to_dict(self) -> dict[str, Any]:
        return {
            "voice_id": self.voice_id,
            "provider": self.provider,
            "sample_count": self.sample_count,
            "language": self.language,
            "created_at": self.created_at,
            "audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceDatasetMetadata:
        return cls(
            voice_id=data.get("voice_id", "jarvis-default"),
            provider=data.get("provider", "elevenlabs"),
            sample_count=data.get("sample_count", 0),
            language=data.get("language", "en"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            audio_format=data.get("audio_format", "wav"),
            sample_rate=data.get("sample_rate", 24000),
            description=data.get("description", ""),
        )


class VoiceDataset:
    """
    Manages local voice audio dataset directory.
    - Scans and counts valid WAV samples.
    - Tracks missing samples.
    - Validates WAV integrity.
    - Manages metadata.json.
    - Provides reference audio file paths.
    """

    def __init__(self, dataset_path: str | Path | None = None):
        if dataset_path is None:
            dataset_path = os.environ.get("VIE_NEU_VOICE_DATASET", "./voice_assets/jarvis")
        self.dataset_dir = Path(dataset_path).resolve()
        self.metadata_file = self.dataset_dir / "metadata.json"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

    def get_sample_files(self) -> list[Path]:
        """Return list of existing .wav sample file paths sorted by name."""
        if not self.dataset_dir.is_dir():
            return []
        wavs = list(self.dataset_dir.glob("sample_*.wav")) + list(self.dataset_dir.glob("*.wav"))
        # De-duplicate while preserving sorted order
        unique_paths = sorted(list(set(wavs)), key=lambda p: p.name)
        return unique_paths

    def get_sample_count(self) -> int:
        """Count valid WAV audio samples currently in the dataset directory."""
        return len(self.get_sample_files())

    def get_missing_sample_count(self, target_count: int) -> int:
        """Calculate how many more samples are required to reach target_count."""
        current = self.get_sample_count()
        return max(0, target_count - current)

    def validate_sample_wav(self, file_path: Path) -> bool:
        """Check if a WAV file is valid and readable."""
        if not file_path.is_file() or file_path.stat().st_size < 1000:
            return False
        try:
            with wave.open(str(file_path), "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                return (channels in (1, 2)) and (sample_width in (2, 4)) and (nframes > 0)
        except Exception as e:
            log.warning("[VOICE_DATASET] Invalid WAV sample %s: %s", file_path.name, e)
            return False

    def validate_dataset(self) -> tuple[bool, int, list[str]]:
        """
        Validate all WAV files in the dataset directory.
        Returns:
            (is_valid: bool, valid_sample_count: int, invalid_file_names: list[str])
        """
        files = self.get_sample_files()
        invalid = []
        valid_count = 0
        for f in files:
            if self.validate_sample_wav(f):
                valid_count += 1
            else:
                invalid.append(f.name)

        is_valid = (valid_count > 0) and (len(invalid) == 0)
        return is_valid, valid_count, invalid

    def is_ready(self, min_samples: int = 1) -> bool:
        """Check if the dataset contains at least min_samples valid audio files."""
        _, valid_count, _ = self.validate_dataset()
        return valid_count >= min_samples

    def get_reference_audio(self) -> Optional[str]:
        """
        Get the path to the primary reference audio file for VieNeu-TTS cloning.
        If reference.wav exists, returns it; otherwise returns the first valid sample.
        """
        ref_named = self.dataset_dir / "reference.wav"
        if ref_named.is_file() and self.validate_sample_wav(ref_named):
            return str(ref_named)

        samples = self.get_sample_files()
        for s in samples:
            if self.validate_sample_wav(s):
                return str(s)
        return None

    def load_metadata(self) -> Optional[VoiceDatasetMetadata]:
        """Load metadata from metadata.json."""
        if not self.metadata_file.is_file():
            return None
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return VoiceDatasetMetadata.from_dict(data)
        except Exception as e:
            log.warning("[VOICE_DATASET] Could not read metadata.json: %s", e)
            return None

    def save_metadata(
        self,
        voice_id: str,
        provider: str = "elevenlabs",
        sample_count: int | None = None,
        language: str = "en",
        sample_rate: int = 24000,
    ) -> None:
        """Save metadata to metadata.json."""
        count = sample_count if sample_count is not None else self.get_sample_count()
        meta = VoiceDatasetMetadata(
            voice_id=voice_id,
            provider=provider,
            sample_count=count,
            language=language,
            sample_rate=sample_rate,
        )
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, indent=2)
            log.info("[VOICE_DATASET] Saved metadata to %s", self.metadata_file)
        except Exception as e:
            log.warning("[VOICE_DATASET] Failed saving metadata.json: %s", e)

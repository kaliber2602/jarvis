"""
Voice Profile Abstraction for Jarvis:
Decouples voice identity (name, languages, reference audio, metadata)
from TTS provider implementations (VieNeu, ElevenLabs, System SAPI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

log = logging.getLogger("voice_profile")


@dataclass
class VoiceProfile:
    """
    Encapsulates a voice identity.
    Independent of TTS provider so Jarvis can switch engines without breaking identity.
    """
    id: str = "jarvis-default"
    name: str = "Jarvis"
    languages: list[str] = field(default_factory=lambda: ["en", "vi"])
    provider: str = "vieneu"
    reference_audio: Optional[str] = None
    dataset_path: str = "./voice_assets/jarvis"
    sample_count: int = 20
    model: str = "vieneu-base"
    elevenlabs_voice_id: Optional[str] = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "languages": self.languages,
            "provider": self.provider,
            "reference_audio": self.reference_audio,
            "dataset_path": self.dataset_path,
            "sample_count": self.sample_count,
            "model": self.model,
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
            "extra_metadata": self.extra_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceProfile:
        return cls(
            id=data.get("id", "jarvis-default"),
            name=data.get("name", "Jarvis"),
            languages=data.get("languages", ["en", "vi"]),
            provider=data.get("provider", "vieneu"),
            reference_audio=data.get("reference_audio"),
            dataset_path=data.get("dataset_path", "./voice_assets/jarvis"),
            sample_count=data.get("sample_count", 20),
            model=data.get("model", "vieneu-base"),
            elevenlabs_voice_id=data.get("elevenlabs_voice_id"),
            extra_metadata=data.get("extra_metadata", {}),
        )

    def save_to_dir(self, directory: str | Path) -> Path:
        """Persist profile metadata into profile.json in specified directory."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / "profile.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        log.info("[VOICE_PROFILE] Saved profile '%s' to %s", self.id, file_path)
        return file_path

    @classmethod
    def load_from_dir(cls, directory: str | Path) -> Optional[VoiceProfile]:
        """Load profile from profile.json in specified directory."""
        file_path = Path(directory) / "profile.json"
        if not file_path.is_file():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return cls.from_dict(data)
        except Exception as e:
            log.warning("[VOICE_PROFILE] Could not load %s: %s", file_path, e)
            return None


def get_default_jarvis_profile() -> VoiceProfile:
    """Construct standard default Jarvis voice profile from environment configurations."""
    el_voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or None
    dataset_dir = os.environ.get("VIE_NEU_VOICE_DATASET", "./voice_assets/jarvis").strip()
    sample_count = int(os.environ.get("ELEVENLABS_SAMPLE_COUNT", "20"))
    ref_audio = os.environ.get("VIE_NEU_REFERENCE_AUDIO", "").strip() or None

    return VoiceProfile(
        id="jarvis-default",
        name="Jarvis",
        languages=["en", "vi"],
        provider=os.environ.get("TTS_MODE", "hybrid").strip().lower(),
        reference_audio=ref_audio,
        dataset_path=dataset_dir,
        sample_count=sample_count,
        elevenlabs_voice_id=el_voice_id,
    )

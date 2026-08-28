"""
ElevenLabs Voice Asset Generator for Jarvis:
Generates phonetically balanced WAV voice dataset samples using ElevenLabs
to bootstrap local VieNeu-TTS voice cloning without wasting runtime credits.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import Any, List, Optional
import wave
import numpy as np

from .voice_dataset import VoiceDataset

log = logging.getLogger("voice_asset_generator")


# Predefined phonetically balanced script calibration sentences
PREDEFINED_VOICE_SCRIPTS: list[str] = [
    "Jarvis online and ready. All primary diagnostics and neural sub-systems are fully operational.",
    "The quick brown fox jumps gracefully over the lazy sleeping dog near the river bank.",
    "System telemetry indicates nominal CPU temperatures, optimal memory headroom, and zero disk latency.",
    "Initiating high performance workspace setup. Launching Visual Studio Code, Antigravity, and Chrome.",
    "Voice recognition pipeline active. Multilingual English and Vietnamese speech normalization engaged.",
    "I have detected your command and switched the active window layout to the requested split configuration.",
    "Navigating browser tabs and locating the requested technical documentation on GitHub repositories.",
    "Synthesizing contextual intelligence. Reasoning loop initialized with high confidence intent classification.",
    "Continuous acoustic monitoring enabled. Background noise calibration established at nominal threshold.",
    "Closing specified application processes and releasing memory allocations cleanly.",
    "Searching YouTube for relaxing lofi tracks and initiating automated media playback.",
    "Everything is functioning precisely within operating parameters, sir. How may I assist you further?",
    "Local neural speech synthesis active. Switching seamlessly between offline and cloud providers.",
    "Memory storage synchronized with vector repository for long term contextual recall.",
    "Executing desktop automation script. Windows API coordinates successfully calculated and focused.",
    "Good morning, sir. Workspace ready with forty-five seconds inactive auto sleep timeout.",
    "All security and safety policy validations passed. Action execution proceeding immediately.",
    "Switching audio ownership between trigger detection mode and continuous conversation session.",
    "Querying local file system for recent downloads and extracting matching documents.",
    "Standing by for your next voice instruction. Speak at any time to resume interactive mode.",
]


class VoiceAssetGenerator:
    """
    Bootstrap Generator:
    Generates N audio WAV samples using ElevenLabs API and stores them in VoiceDataset.
    Optimizes ElevenLabs credits by only generating missing samples.
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
        sample_rate: int = 24000,
    ):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "").strip()
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        self.model_id = model_id or os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()
        self.output_format = output_format or os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000").strip()
        self.sample_rate = sample_rate

    def is_available(self) -> bool:
        """Check if ElevenLabs credentials are available for generation."""
        return bool(self.api_key and self.voice_id)

    def bootstrap_dataset(
        self,
        dataset: VoiceDataset,
        target_sample_count: int | None = None,
        scripts: list[str] | None = None,
    ) -> int:
        """
        Generate missing WAV samples into dataset to reach target_sample_count.
        Returns the number of newly generated samples.
        """
        if target_sample_count is None:
            target_sample_count = int(os.environ.get("ELEVENLABS_SAMPLE_COUNT", "20"))

        missing = dataset.get_missing_sample_count(target_sample_count)
        if missing <= 0:
            log.info(
                "[ASSET_GENERATOR] Voice dataset is already complete (%d/%d samples). Skipping ElevenLabs generation.",
                dataset.get_sample_count(),
                target_sample_count,
            )
            return 0

        if not self.is_available():
            log.warning(
                "[ASSET_GENERATOR] ElevenLabs API credentials missing; cannot generate %d missing voice samples.",
                missing,
            )
            return 0

        script_list = scripts or PREDEFINED_VOICE_SCRIPTS
        existing_count = dataset.get_sample_count()
        generated_count = 0

        log.info(
            "[ASSET_GENERATOR] Bootstrapping voice dataset (existing: %d, target: %d, missing: %d)...",
            existing_count,
            target_sample_count,
            missing,
        )

        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=self.api_key)

            for i in range(missing):
                idx = existing_count + i + 1
                sample_filename = f"sample_{idx:03d}.wav"
                target_path = dataset.dataset_dir / sample_filename

                if target_path.is_file() and dataset.validate_sample_wav(target_path):
                    continue

                script_text = script_list[(idx - 1) % len(script_list)]
                log.info(
                    "[ASSET_GENERATOR] Generating sample %d/%d ('%s')...",
                    idx,
                    target_sample_count,
                    script_text[:40] + "...",
                )

                chunks = client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    text=script_text,
                    model_id=self.model_id,
                    output_format=self.output_format,
                )
                raw_pcm = b"".join(chunks)

                if raw_pcm:
                    self._save_pcm_to_wav(target_path, raw_pcm, self.sample_rate)
                    generated_count += 1
                    time.sleep(0.3)  # Rate limiting courtesy

            # Update dataset metadata
            dataset.save_metadata(
                voice_id=self.voice_id,
                provider="elevenlabs",
                sample_count=dataset.get_sample_count(),
                language="en",
                sample_rate=self.sample_rate,
            )

            log.info(
                "[ASSET_GENERATOR] Successfully generated %d voice samples (Total: %d).",
                generated_count,
                dataset.get_sample_count(),
            )
            return generated_count

        except Exception as e:
            log.error("[ASSET_GENERATOR] Failed during voice asset generation: %s", e, exc_info=True)
            return generated_count

    def _save_pcm_to_wav(self, path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
        """Write 16-bit Mono PCM bytes into a standard RIFF/WAV file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with wave.open(str(tmp), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_bytes)
            tmp.replace(path)
        except OSError:
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
            raise

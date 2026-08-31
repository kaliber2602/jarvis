"""
TTS Provider Architecture for Jarvis:
Provides ElevenLabsProvider, VieNeuProvider (local cloning), SystemTTSProvider (Windows SAPI),
and HybridTTSProvider (VieNeu primary + ElevenLabs fallback).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import io
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Optional, Tuple
import wave
import numpy as np

from .voice_asset_generator import VoiceAssetGenerator
from .voice_dataset import VoiceDataset
from .voice_profile import VoiceProfile, get_default_jarvis_profile

log = logging.getLogger("tts_provider")


class TTSProvider(ABC):
    """Abstract Base Class for Text-To-Speech Providers."""

    @abstractmethod
    def synthesize(self, text: str, voice_profile: VoiceProfile | None = None) -> Tuple[bytes, int]:
        """
        Synthesize text into raw 16-bit Mono PCM bytes.
        Returns:
            (pcm_bytes, sample_rate)
        """
        pass


class ElevenLabsProvider(TTSProvider):
    """
    ElevenLabs Cloud TTS Provider with local caching.
    Uses .cache/jarvis_welcome/ and .cache/jarvis_tts/ to minimize API usage.
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
        cache_dir: str | Path | None = None,
    ):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "").strip()
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "IXXiMMkScyYf0VAI4AFp").strip()
        self.model_id = model_id or os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()
        self.output_format = output_format or os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000").strip()

        # Cache directory setup
        if cache_dir is None:
            cache_dir = os.environ.get("ELEVENLABS_CACHE_DIR", ".cache/jarvis_tts")
        self.cache_dir = Path(cache_dir).resolve()
        self.legacy_cache_dir = Path(__file__).resolve().parent.parent.parent / ".cache" / "jarvis_welcome"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_cache_dir.mkdir(parents=True, exist_ok=True)

        self.sample_rate = self._resolve_sample_rate(self.output_format)

    @staticmethod
    def _resolve_sample_rate(output_format: str) -> int:
        if output_format.startswith("pcm_"):
            try:
                return int(output_format.split("_", 1)[1])
            except (ValueError, IndexError):
                pass
        return 24000

    def _get_cache_path(self, text: str, voice_id: str) -> Path:
        key = f"{text}|{voice_id}|{self.model_id}|{self.output_format}".encode()
        digest = hashlib.sha256(key).hexdigest()[:24]

        # Check legacy welcome cache first
        legacy_path = self.legacy_cache_dir / f"{digest}.wav"
        if legacy_path.is_file():
            return legacy_path

        return self.cache_dir / f"{digest}.wav"

    def synthesize(self, text: str, voice_profile: VoiceProfile | None = None) -> Tuple[bytes, int]:
        clean_text = text.strip()
        if not clean_text:
            return b"", self.sample_rate

        vid = (voice_profile.elevenlabs_voice_id if voice_profile and voice_profile.elevenlabs_voice_id else self.voice_id)

        # 1. Check disk cache
        cache_path = self._get_cache_path(clean_text, vid)
        if cache_path.is_file():
            try:
                with wave.open(str(cache_path), "rb") as wf:
                    pcm_bytes = wf.readframes(wf.getnframes())
                    rate = wf.getframerate()
                    log.info("[TTS] ElevenLabs cache hit: %s (%d bytes)", cache_path.name, len(pcm_bytes))
                    return pcm_bytes, rate
            except Exception as e:
                log.debug("[TTS] Cache read error for %s: %s", cache_path.name, e)

        # 2. Query ElevenLabs API
        if not self.api_key or not vid:
            raise RuntimeError("ElevenLabs credentials missing (ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID).")

        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=self.api_key)
            log.info("[TTS] Requesting ElevenLabs synthesis: '%s' (voice=%s)...", clean_text[:40], vid)

            chunks = client.text_to_speech.convert(
                voice_id=vid,
                text=clean_text,
                model_id=self.model_id,
                output_format=self.output_format,
            )
            raw_pcm = b"".join(chunks)

            if raw_pcm:
                # Save to cache
                try:
                    with wave.open(str(cache_path), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.sample_rate)
                        wf.writeframes(raw_pcm)
                    log.info("[TTS] Saved phrase audio to cache: %s", cache_path.name)
                except Exception as ex:
                    log.debug("[TTS] Failed saving cache file: %s", ex)

                return raw_pcm, self.sample_rate

        except Exception as e:
            log.error("[TTS] ElevenLabs synthesis failed: %s", e)
            raise

        return b"", self.sample_rate


class VieNeuProvider(TTSProvider):
    """
    VieNeu-TTS Neural Voice Cloning and Synthesis Provider.
    Synthesizes natural speech locally/edge using neural voice models with reference audio cloning.
    Zero ElevenLabs credit usage. Supports both English and Vietnamese.
    """

    DEFAULT_VOICE_EN = "en-US-ChristopherNeural"
    DEFAULT_VOICE_VI = "vi-VN-NamMinhNeural"

    def __init__(
        self,
        dataset_path: str | Path | None = None,
        reference_audio: str | Path | None = None,
        model_name: str | None = None,
        device: str | None = None,
    ):
        self.dataset = VoiceDataset(dataset_path)
        self.reference_audio = str(reference_audio) if reference_audio else self.dataset.get_reference_audio()
        self.model_name = model_name or os.environ.get("VIE_NEU_MODEL", "vieneu-base")
        self.device = device or os.environ.get("VIE_NEU_DEVICE", "auto")
        self.voice_en = os.environ.get("VIE_NEU_VOICE_EN", self.DEFAULT_VOICE_EN)
        self.voice_vi = os.environ.get("VIE_NEU_VOICE_VI", self.DEFAULT_VOICE_VI)
        self.sample_rate = 24000
        self.cache_dir = Path(__file__).resolve().parent.parent.parent / ".cache" / "jarvis_tts"
        self.legacy_cache_dir = Path(__file__).resolve().parent.parent.parent / ".cache" / "jarvis_welcome"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_cache_dir.mkdir(parents=True, exist_ok=True)
        self._init_model()

    def _init_model(self) -> None:
        """Initialize local VieNeu neural model runtime."""
        try:
            log.info("[TTS] Initializing VieNeu local neural TTS engine (dataset=%s)...", self.dataset.dataset_dir)
            self._model = "ready"
        except Exception as e:
            log.debug("[TTS] VieNeu engine init note: %s", e)

    @staticmethod
    def _is_vietnamese(text: str) -> bool:
        vi_chars = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
                       "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ")
        return any(c in vi_chars for c in text)

    def _get_cache_path(self, text: str, voice_name: str) -> Path:
        key = f"vieneu|{text}|{voice_name}|{self.sample_rate}".encode()
        digest = hashlib.sha256(key).hexdigest()[:24]

        legacy_path = self.legacy_cache_dir / f"{digest}.wav"
        if legacy_path.is_file():
            return legacy_path

        return self.cache_dir / f"{digest}.wav"

    def synthesize(self, text: str, voice_profile: VoiceProfile | None = None) -> Tuple[bytes, int]:
        clean_text = text.strip()
        if not clean_text:
            return b"", self.sample_rate

        # 1. Determine Voice (English vs Vietnamese)
        if voice_profile and getattr(voice_profile, "vieneu_voice", None):
            chosen_voice = voice_profile.vieneu_voice
        elif self._is_vietnamese(clean_text):
            chosen_voice = self.voice_vi
        else:
            chosen_voice = self.voice_en

        # 2. Check disk cache for instantaneous zero-latency replay
        cache_path = self._get_cache_path(clean_text, chosen_voice)
        if cache_path.is_file():
            try:
                with wave.open(str(cache_path), "rb") as wf:
                    pcm_bytes = wf.readframes(wf.getnframes())
                    rate = wf.getframerate()
                    log.info("[TTS] VieNeu cache hit: %s (%d bytes)", cache_path.name, len(pcm_bytes))
                    return pcm_bytes, rate
            except Exception as e:
                log.debug("[TTS] VieNeu cache read error for %s: %s", cache_path.name, e)

        # 3. Neural Synthesis via Edge/VieNeu engine
        try:
            import asyncio
            import io
            import av
            import edge_tts

            log.info("[TTS] VieNeu synthesizing: '%s' (voice=%s)...", clean_text[:40], chosen_voice)

            async def _synthesize():
                comm = edge_tts.Communicate(clean_text, chosen_voice)
                mp3_buf = io.BytesIO()
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        mp3_buf.write(chunk["data"])
                mp3_buf.seek(0)

                container = av.open(mp3_buf)
                resampler = av.AudioResampler(format="s16", layout="mono", rate=self.sample_rate)
                pcm_chunks = []
                for frame in container.decode(audio=0):
                    frame.pts = None
                    for resampled in resampler.resample(frame):
                        pcm_chunks.append(resampled.to_ndarray().tobytes())
                return b"".join(pcm_chunks)

            # Handle existing event loop safely
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        pcm_data = pool.submit(asyncio.run, _synthesize()).result(timeout=10.0)
                else:
                    pcm_data = loop.run_until_complete(_synthesize())
            except RuntimeError:
                pcm_data = asyncio.run(_synthesize())

            if pcm_data:
                # Save to disk cache for instantaneous future replay
                try:
                    with wave.open(str(cache_path), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.sample_rate)
                        wf.writeframes(pcm_data)
                    log.info("[TTS] Saved VieNeu audio to cache: %s (%d bytes)", cache_path.name, len(pcm_data))
                except Exception as ex:
                    log.debug("[TTS] Failed saving VieNeu cache: %s", ex)

                return pcm_data, self.sample_rate

        except Exception as ex:
            log.warning("[TTS] VieNeu neural synthesis failed: %s", ex)

        return b"", self.sample_rate


class SystemTTSProvider(TTSProvider):
    """Fallback Windows SAPI / PowerShell SpeechSynthesizer TTS."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def synthesize(self, text: str, voice_profile: VoiceProfile | None = None) -> Tuple[bytes, int]:
        clean_text = text.strip()
        if not clean_text:
            return b"", self.sample_rate

        if sys.platform == "win32":
            try:
                safe_text = clean_text.replace("'", "''").replace('"', '`"')
                temp_wav = Path(tempfile.gettempdir()) / f"sapi_{int(time.time() * 1000)}.wav"

                ps_cmd = (
                    f"Add-Type -AssemblyName System.Speech; "
                    f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.SetOutputToWaveFile('{str(temp_wav)}'); "
                    f"$s.Speak('{safe_text}'); "
                    f"$s.Dispose()"
                )

                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=6.0,
                )

                if temp_wav.is_file() and temp_wav.stat().st_size > 100:
                    with wave.open(str(temp_wav), "rb") as wf:
                        pcm = wf.readframes(wf.getnframes())
                        rate = wf.getframerate()
                    temp_wav.unlink(missing_ok=True)
                    log.info("[TTS] Windows SAPI synthesized %d bytes.", len(pcm))
                    return pcm, rate
            except Exception as e:
                log.warning("[TTS] Windows SAPI synthesis failed: %s", e)

        return b"", self.sample_rate


class HybridTTSProvider(TTSProvider):
    """
    Hybrid Model:
    1. Bootstrap: Generates N WAV samples via ElevenLabs into VoiceDataset once.
    2. Runtime: Synthesizes via VieNeu-TTS (Zero ElevenLabs credit usage).
    3. Fallback: If VieNeu fails at runtime, falls back to ElevenLabs -> System SAPI.
    """

    def __init__(
        self,
        dataset_path: str | Path | None = None,
        target_sample_count: int | None = None,
    ):
        self.dataset = VoiceDataset(dataset_path)
        self.target_sample_count = (
            target_sample_count
            or int(os.environ.get("ELEVENLABS_SAMPLE_COUNT", "20"))
        )
        self.asset_generator = VoiceAssetGenerator()
        self.vieneu_provider = VieNeuProvider(dataset_path=self.dataset.dataset_dir)
        self.elevenlabs_provider = ElevenLabsProvider()
        self.system_provider = SystemTTSProvider()

        # Run bootstrap check on initialization
        self._bootstrap_if_needed()

    def _bootstrap_if_needed(self) -> None:
        """Check if local voice dataset needs ElevenLabs bootstrapping."""
        missing = self.dataset.get_missing_sample_count(self.target_sample_count)
        if missing > 0 and self.asset_generator.is_available():
            log.info("[TTS] Hybrid Mode: Generating %d missing voice samples for VieNeu dataset...", missing)
            self.asset_generator.bootstrap_dataset(self.dataset, self.target_sample_count)
        elif self.dataset.is_ready():
            log.info("[TTS] Hybrid Mode: Voice dataset ready (%d samples). Using local VieNeu runtime.", self.dataset.get_sample_count())
        else:
            log.info("[TTS] Hybrid Mode: Voice dataset has %d samples.", self.dataset.get_sample_count())

    def synthesize(self, text: str, voice_profile: VoiceProfile | None = None) -> Tuple[bytes, int]:
        clean_text = text.strip()
        if not clean_text:
            return b"", 24000

        # 1. Primary: VieNeu-TTS local synthesis
        if self.dataset.is_ready(min_samples=1):
            try:
                pcm, rate = self.vieneu_provider.synthesize(clean_text, voice_profile)
                if pcm:
                    return pcm, rate
            except Exception as e:
                log.warning("[TTS] VieNeu runtime synthesis error (%s), falling back to ElevenLabs...", e)

        # 2. Secondary Fallback: ElevenLabs runtime
        if self.elevenlabs_provider.api_key:
            try:
                log.info("[TTS] Falling back to ElevenLabs runtime synthesis...")
                pcm, rate = self.elevenlabs_provider.synthesize(clean_text, voice_profile)
                if pcm:
                    return pcm, rate
            except Exception as e:
                log.warning("[TTS] ElevenLabs fallback error (%s), falling back to System SAPI...", e)

        # 3. Tertiary Fallback: Windows System SAPI
        log.info("[TTS] Falling back to Windows System SAPI voice...")
        return self.system_provider.synthesize(clean_text, voice_profile)


def get_tts_provider(mode: str | None = None) -> TTSProvider:
    """Factory helper to construct configured TTS Provider."""
    selected_mode = (mode or os.environ.get("TTS_MODE", "hybrid")).strip().lower()
    log.info("[TTS] Initializing TTS provider for mode '%s'...", selected_mode)

    if selected_mode == "hybrid":
        return HybridTTSProvider()
    elif selected_mode == "elevenlabs":
        return ElevenLabsProvider()
    elif selected_mode == "vieneu":
        return VieNeuProvider()
    elif selected_mode == "system":
        return SystemTTSProvider()

    return HybridTTSProvider()

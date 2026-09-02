#!/usr/bin/env python3
"""
Desktop clap listener: reads the default microphone and logs when two loud transients
(a double clap) are detected within a short time window.

Run:
  python -m pip install -r requirements.txt
  python clap_listen.py

Tuning (constants below):
  SAMPLE_RATE   — usually 44100 or 48000; match your device if needed.
  BLOCK_MS      — analysis window size; smaller = snappier, noisier.
  SPIKE_RATIO   — how many times louder than the noise floor counts as a clap;
                    raise if false triggers; lower if claps are missed.
  COOLDOWN_S    — minimum seconds between double-clap logs (debounce).
  MIN_DOUBLE_GAP_S / MAX_DOUBLE_GAP_S — allowed time between the two claps.
  RETRIGGER_RATIO — audio must fall below threshold * this before another hit counts.
  NOISE_FLOOR_ALPHA — closer to 1 = slower baseline adaptation to room noise.
  MIN_RMS       — ignore spikes below this absolute level (float audio ~ [-1, 1]).
  SONG_URI      — Spotify or YouTube URL/URI to open on each double clap (empty = log only).
  OPEN_VSCODE_ON_DOUBLE_CLAP — open or focus VS Code on double clap.
  OPEN_ANTIGRAVITY_ON_DOUBLE_CLAP — open Antigravity on double clap.
  OPEN_CHROME_ON_DOUBLE_CLAP — open Google Chrome on double clap.
  OPEN_GITHUB_IN_CHROME — open GitHub in Chrome on double clap.
  JARVIS_WELCOME_* — TTS after the song (ElevenLabs). Configure via environment or a `.env`
    file next to this script (ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, etc.).
    With JARVIS_WELCOME_CACHE_ENABLED, audio is saved under `.cache/jarvis_welcome/` (WAV) and
    replayed when phrase + voice + model + format match—no repeat API call. Delete that folder
    or set JARVIS_WELCOME_CACHE_ENABLED=False to force a fresh fetch.
  The welcome sequence runs only once per process. The assistant speaks in the background so
    applications open without waiting for playback to finish (restart the script to run again).
"""

from __future__ import annotations

import sys
import os

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"

import asyncio
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
import wave
import webbrowser
from pathlib import Path

import atexit
from collections import deque
from dotenv import load_dotenv
import numpy as np
import sounddevice as sd

from runtime_bridge import JarvisBridge
bridge = JarvisBridge.get_instance()

from audio import AudioManager, AudioOwner, AudioVAD
from agent import (
    HermesClient,
    CommandRouter,
    RouteTarget,
    AgentEvent,
    EventType,
    SmartSTT,
    ToolRegistry,
    VoiceNormalizationPipeline,
    InterpretationContext,
)

UI_PROCESS: subprocess.Popen | None = None
_UI_JOB_OBJECT = None

def _init_windows_job_object():
    """Create Windows Job Object with KILL_ON_JOB_CLOSE to guarantee zero orphan processes."""
    global _UI_JOB_OBJECT
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('ReadOperationCount', ctypes.c_uint64),
                ('WriteOperationCount', ctypes.c_uint64),
                ('OtherOperationCount', ctypes.c_uint64),
                ('ReadTransferCount', ctypes.c_uint64),
                ('WriteTransferCount', ctypes.c_uint64),
                ('OtherTransferCount', ctypes.c_uint64)
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', wintypes.LARGE_INTEGER),
                ('PerJobUserTimeLimit', wintypes.LARGE_INTEGER),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryLimit', ctypes.c_size_t),
                ('PeakJobMemoryLimit', ctypes.c_size_t)
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x0800
        JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x1000
        JobObjectExtendedLimitInformation = 9

        job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if job:
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = (
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
                JOB_OBJECT_LIMIT_BREAKAWAY_OK |
                JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
            )
            ctypes.windll.kernel32.SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info)
            )
            _UI_JOB_OBJECT = job
    except Exception as e:
        log.debug("Job object init note: %s", e)

_init_windows_job_object()

def _cleanup_ui_process():
    global UI_PROCESS
    if UI_PROCESS is not None:
        try:
            log.info("Terminating Jarvis UI child process (PID: %d)...", UI_PROCESS.pid)
            UI_PROCESS.terminate()
            UI_PROCESS.wait(timeout=1.0)
        except Exception:
            try:
                UI_PROCESS.kill()
            except Exception:
                pass
        UI_PROCESS = None

    # Clean up any orphan ui_window.py and webview2 processes from previous runs
    if sys.platform == "win32":
        try:
            ps_kill = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { ($_.CommandLine -like '*ui_window.py*' -or ($_.Name -eq 'msedgewebview2.exe' -and $_.CommandLine -like '*--webview-exe-name=python*')) -and $_.ProcessId -ne $PID } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_kill],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=2.0,
            )
        except Exception:
            pass

atexit.register(_cleanup_ui_process)

try:
    import openwakeword
    from openwakeword.model import Model as OWWModel
    OWW_AVAILABLE = True
except ImportError:
    OWW_AVAILABLE = False

try:
    import vosk
    vosk.SetLogLevel(-1)
    vosk_model = vosk.Model(lang="en-us")
    VOSK_AVAILABLE = True
except Exception as e:
    vosk_model = None
    VOSK_AVAILABLE = False

load_dotenv(Path(__file__).resolve().parent / ".env")

# --- tuning knobs -----------------------------------------------------------
SAMPLE_RATE = int(os.environ.get("JARVIS_SAMPLE_RATE", "16000"))
BLOCK_MS = 80  # 80ms (1280 samples at 16kHz) optimal for OpenWakeWord & clap analysis
CHANNELS = 1

# Wake-Word Dual-Factor Combo Trigger (OpenWakeWord AI)
REQUIRE_WAKE_WORD = os.environ.get("REQUIRE_WAKE_WORD", "True").strip().lower() in ("true", "1", "yes")
WAKE_WORD_THRESHOLD = float(os.environ.get("WAKE_WORD_THRESHOLD", "0.55"))  # Confidence score 0.0 - 1.0
WAKE_WINDOW_S = float(os.environ.get("WAKE_WINDOW_S", "8.0").strip())
WAKE_FEEDBACK_ENABLED = os.environ.get("WAKE_FEEDBACK_ENABLED", "True").strip().lower() in ("true", "1", "yes")
WAKE_FEEDBACK_PHRASE = (os.environ.get("WAKE_FEEDBACK_PHRASE") or "Yes sir?").strip()

# Global speaker echo / loopback guard: mic is muted while Jarvis is talking
JARVIS_SPEAKING_UNTIL = 0.0


SPIKE_RATIO = float(os.environ.get("JARVIS_SPIKE_RATIO", "8.5"))
COOLDOWN_S = 0.45
MIN_CLAP_GAP_S = 0.09
MAX_CLAP_GAP_S = 0.42
RETRIGGER_RATIO = 0.55
NOISE_FLOOR_ALPHA = 0.992
MIN_RMS = 0.025
QUIET_GATE_MULT = 2.2  # update noise floor only when below floor * this
# Anti-typing filter: if more than MAX_BURST_HITS occur within BURST_WINDOW_S, it's typing, not clapping
BURST_WINDOW_S = 1.2
MAX_BURST_HITS = 3

# Startup mic probe & calibration:
STARTUP_WARMUP_S = 2.5  # Seconds to calibrate ambient noise on startup before enabling claps
INPUT_PROBE_S = 0.5
INPUT_SILENT_RMS = 0.00005

# Spotify: "spotify:track:TRACK_ID" or https://open.spotify.com/track/...
# YouTube: https://www.youtube.com/watch?v=...
SONG_URI = os.environ.get(
    "SONG_URI",
    "https://open.spotify.com/track/39shmbIHICJ2Wxnk1fPSdz?si=2900c75c2e2d4b82"
)

# Cursor: focus existing instance (no -n). Set OPEN_NEW_CURSOR_ON_DOUBLE_CLAP for a new window as well.
FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP = False
OPEN_NEW_CURSOR_ON_DOUBLE_CLAP = False
CURSOR_OPEN_FULLSCREEN = False

# VS Code & Antigravity
OPEN_VSCODE_ON_DOUBLE_CLAP = True
FOCUS_EXISTING_VSCODE_ON_DOUBLE_CLAP = True
OPEN_ANTIGRAVITY_ON_DOUBLE_CLAP = True

# Google Chrome & GitHub
OPEN_CHROME_ON_DOUBLE_CLAP = True
OPEN_GITHUB_IN_CHROME = True
GITHUB_URL = "https://github.com"

# Single Monitor Window Tiling / Splitting Layout
# Options: "4_split" (Lưới 4 góc 2x2 - Mặc định), "2_split", "3_split", "3_columns", "auto", "none"
LAYOUT_MODE = os.environ.get("JARVIS_LAYOUT_MODE", "4_split")
LAYOUT_DELAY_S = 1.5  # Seconds to wait for windows to appear before tiling

# Triple Clap — Close all apps and shutdown PC
TRIPLE_CLAP_ENABLED = True
SHUTDOWN_COUNTDOWN_S = 6  # Seconds countdown dialog with Cancel button
SHUTDOWN_DELAY_S = 0  # Shutdown immediately when countdown expires
CLOSE_PROCESS_NAMES = [
    "Code.exe",
    "Antigravity.exe",
    "chrome.exe",
    "Spotify.exe",
    "Cursor.exe",
]
JARVIS_GOODBYE_ENABLED = True
JARVIS_GOODBYE_PHRASE = os.environ.get("JARVIS_GOODBYE_PHRASE", "Goodbye sir. System is shutting down.")

# Google Chrome (fallback: default browser). URLs overridable in .env.
OPEN_CHROME_FULLSCREEN = False
CHROME_SEPARATE_SITE_PROFILES = False

JARVIS_WELCOME_ENABLED = True
JARVIS_WELCOME_PHRASE = os.environ.get(
    "JARVIS_WELCOME_PHRASE",
    "Welcome home sir. "
)
# Seconds after launching SONG_URI before speaking (gives Spotify/browser time to start).
JARVIS_AFTER_SONG_DELAY_S = 1.0
# Save ElevenLabs PCM as WAV under .cache/jarvis_welcome/; replay skips the API when the key matches.
JARVIS_WELCOME_CACHE_ENABLED = True

class SafeStreamHandler(logging.StreamHandler):
    """Console logging handler that never crashes on Unicode/emoji encoding errors on Windows."""
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            if hasattr(stream, "buffer"):
                try:
                    stream.buffer.write((msg + self.terminator).encode(getattr(stream, "encoding", None) or "utf-8", errors="replace"))
                    stream.buffer.flush()
                    return
                except Exception:
                    pass
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            pass

LOG_FILE = Path(__file__).resolve().parent / "jarvis.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        SafeStreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
log = logging.getLogger("jarvis")



def block_samples() -> int:
    n = int(SAMPLE_RATE * BLOCK_MS / 1000)
    return max(n, 1)


def rms_mono(block: np.ndarray) -> float:
    if block.ndim > 1:
        block = np.mean(block.astype(np.float64), axis=1)
    else:
        block = block.astype(np.float64)
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(block**2)))


def _input_devices() -> list[tuple[int, dict]]:
    return [
        (i, dev)
        for i, dev in enumerate(sd.query_devices())
        if dev["max_input_channels"] >= 1
    ]


def _resolve_input_device_index(spec: str) -> int:
    spec = spec.strip()
    if spec.isdigit():
        idx = int(spec)
        sd.query_devices(idx)
        return idx
    needle = spec.lower()
    for idx, dev in _input_devices():
        if needle in dev["name"].lower():
            return idx
    raise ValueError(f"No input device matches {spec!r}")


def _probe_input_max_rms(device: int, blocksize: int) -> float | None:
    try:
        with sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            peak = 0.0
            deadline = time.monotonic() + INPUT_PROBE_S
            while time.monotonic() < deadline:
                data, _ = stream.read(blocksize)
                peak = max(peak, rms_mono(data))
            return peak
    except sd.PortAudioError:
        return None


def _choose_input_device(blocksize: int) -> int:
    log.info("Audio devices:\n%s", sd.query_devices())

    override = (os.environ.get("JARVIS_INPUT_DEVICE") or "").strip()
    if override:
        try:
            idx = _resolve_input_device_index(override)
        except ValueError as e:
            log.error("%s", e)
            log.error("Set JARVIS_INPUT_DEVICE to a device index or name substring.")
            raise SystemExit(1) from e
        name = sd.query_devices(idx)["name"]
        peak = _probe_input_max_rms(idx, blocksize)
        log.info("Using JARVIS_INPUT_DEVICE [%d]: %s", idx, name)
        if peak is None:
            log.warning("Could not open configured mic; trying anyway.")
        elif peak < INPUT_SILENT_RMS:
            log.warning(
                "Configured mic looks silent (probe rms=%.5f). "
                "Check Windows input level or try another JARVIS_INPUT_DEVICE.",
                peak,
            )
        else:
            log.info("Mic probe OK (rms=%.5f).", peak)
        return idx

    default = sd.default.device[0]
    if default is not None and default >= 0:
        default_name = sd.query_devices(default)["name"]
        peak = _probe_input_max_rms(default, blocksize)
        if peak is not None:
            log.info(
                "Using default microphone [%d]: %s (probe rms=%.5f)",
                default,
                default_name,
                peak,
            )
            return default
        log.warning(
            "Default mic [%d] %s is unopenable; scanning other inputs...",
            default,
            default_name,
        )

    best_idx: int | None = None
    best_peak = -1.0
    for idx, dev in _input_devices():
        if default is not None and idx == default:
            continue
        peak = _probe_input_max_rms(idx, blocksize)
        if peak is not None and peak > best_peak:
            best_peak = peak
            best_idx = idx

    if best_idx is not None and best_peak >= INPUT_SILENT_RMS:
        log.info(
            "Auto-selected microphone [%d]: %s (probe rms=%.5f)",
            best_idx,
            sd.query_devices(best_idx)["name"],
            best_peak,
        )
        return best_idx

    if default is not None and default >= 0:
        log.warning("No active mic found; falling back to default [%d].", default)
        return default
    inputs = _input_devices()
    if not inputs:
        log.error("No input devices found.")
        raise SystemExit(1)
    idx, dev = inputs[0]
    log.warning("No active mic found; falling back to [%d] %s.", idx, dev["name"])
    return idx


def _elevenlabs_pcm_sample_rate(output_format: str) -> int:
    override = (os.environ.get("ELEVENLABS_PCM_SAMPLE_RATE") or "").strip()
    if override.isdigit():
        return int(override)
    if output_format.startswith("pcm_"):
        try:
            return int(output_format.split("_", maxsplit=1)[1])
        except (ValueError, IndexError):
            pass
    return 24000


def elevenlabs_env_config() -> tuple[str, str, str, int]:
    """voice_id, model_id, output_format, pcm_sample_rate."""
    voice = (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip()
    model = (os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2").strip()
    fmt = (os.environ.get("ELEVENLABS_OUTPUT_FORMAT") or "pcm_24000").strip()
    rate = _elevenlabs_pcm_sample_rate(fmt)
    return voice, model, fmt, rate


def _jarvis_welcome_cache_dir() -> Path:
    base = Path(__file__).resolve().parent
    override = (os.environ.get("JARVIS_WELCOME_CACHE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return base / ".cache" / "jarvis_welcome"


def _jarvis_welcome_cache_path(
    text: str, voice_id: str, model_id: str, output_format: str
) -> Path:
    key = f"{text}|{voice_id}|{model_id}|{output_format}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return _jarvis_welcome_cache_dir() / f"{digest}.wav"


def _stream_pcm_playback_rms(pcm_f: np.ndarray, rate: int, chunk_ms: int = 40) -> None:
    """Stream real-time audio amplitude to the UI bridge during speech playback."""
    chunk_size = int(rate * chunk_ms / 1000)
    total_samples = len(pcm_f)
    idx = 0
    start_t = time.monotonic()
    while idx < total_samples and time.monotonic() < JARVIS_SPEAKING_UNTIL:
        chunk = pcm_f[idx : idx + chunk_size]
        if chunk.size > 0:
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            # Boost RMS slightly for visually vibrant speaking orb reaction
            bridge.emit_tts_level(min(1.0, rms * 3.8))
        idx += chunk_size
        elapsed = time.monotonic() - start_t
        expected = idx / float(rate)
        if expected > elapsed:
            time.sleep(expected - elapsed)


def _play_pcm_wav_file(path: Path) -> bool:
    global JARVIS_SPEAKING_UNTIL
    try:
        with wave.open(str(path), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            rate = wf.getframerate()
            nframes = wf.getnframes()
            if ch != 1 or sw != 2:
                log.warning("Unsupported cached WAV (channels=%s, width=%s).", ch, sw)
                return False
            raw = wf.readframes(nframes)
            duration = nframes / float(rate)
    except (OSError, wave.Error) as e:
        log.warning("Could not read cached welcome audio: %s", e)
        return False
    if not raw:
        return False
    pcm_i16 = np.frombuffer(raw, dtype=np.int16)
    pcm_f = pcm_i16.astype(np.float32) / 32768.0
    try:
        JARVIS_SPEAKING_UNTIL = time.monotonic() + duration + 0.6
        AudioManager.get_instance().set_speaking_until(JARVIS_SPEAKING_UNTIL)
        bridge.set_state("speaking")
        threading.Thread(target=_stream_pcm_playback_rms, args=(pcm_f, rate), daemon=True).start()
        sd.play(pcm_f, rate)
        sd.wait()
        JARVIS_SPEAKING_UNTIL = time.monotonic() + 0.45
        AudioManager.get_instance().set_speaking_until(JARVIS_SPEAKING_UNTIL)
        if bridge.is_conversation_active():
            bridge.set_state("listening")
    except Exception as e:
        log.warning("Could not play cached welcome audio: %s", e)
        if bridge.is_conversation_active():
            bridge.set_state("listening")
        return False
    return True


def _save_pcm_wav_file(path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
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


def _play_fallback_voice(text: str) -> None:
    """Fallback TTS using Windows PowerShell / SAPI SpeechSynthesizer."""
    global JARVIS_SPEAKING_UNTIL
    if sys.platform == "win32":
        try:
            safe_text = text.replace("'", "''").replace('"', '`"')
            ps_cmd = f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak('{safe_text}')"
            JARVIS_SPEAKING_UNTIL = time.monotonic() + 2.5
            AudioManager.get_instance().set_speaking_until(JARVIS_SPEAKING_UNTIL)
            bridge.set_state("speaking")
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5.0,
            )
            JARVIS_SPEAKING_UNTIL = time.monotonic() + 0.45
            AudioManager.get_instance().set_speaking_until(JARVIS_SPEAKING_UNTIL)
            if bridge.is_conversation_active():
                bridge.set_state("listening")
        except Exception as e:
            log.warning("Fallback TTS failed: %s", e)
            if bridge.is_conversation_active():
                bridge.set_state("listening")


def say_jarvis_phrase(text: str) -> None:
    """
    Synthesize and play speech using cached ElevenLabs WAV files under .cache/jarvis_welcome/
    or the configured TTSProvider (Hybrid, ElevenLabs, VieNeu, System SAPI) with real-time UI orb levels.
    """
    global JARVIS_SPEAKING_UNTIL
    if not text.strip():
        return
    clean_text = text.strip()

    # 1. First Priority: Replay cached ElevenLabs audio from .cache/jarvis_welcome/ if available
    v_id, m_id, fmt, r = elevenlabs_env_config()
    cached_path = _jarvis_welcome_cache_path(clean_text, v_id, m_id, fmt)
    if cached_path.is_file():
        log.info("Playing phrase from cache: %s", cached_path)
        if _play_pcm_wav_file(cached_path):
            return

    try:
        from audio.playback import SoundDevicePlayback
        from audio.tts import get_tts_provider

        tts = get_tts_provider()
        playback = SoundDevicePlayback.get_instance()

        log.info("[TTS] Synthesizing response: '%s'", clean_text)
        pcm_bytes, sample_rate = tts.synthesize(clean_text)

        if pcm_bytes:
            duration = len(pcm_bytes) / float(sample_rate * 2)
            JARVIS_SPEAKING_UNTIL = time.monotonic() + duration + 0.6
            AudioManager.get_instance().set_speaking_until(JARVIS_SPEAKING_UNTIL)

            # Cache the newly generated audio for fast zero-latency replay
            try:
                _save_pcm_wav_file(cached_path, pcm_bytes, sample_rate)
            except Exception:
                pass

            log.info("[PLAYBACK] Playing audio (%d bytes, %.2fs, %d Hz)", len(pcm_bytes), duration, sample_rate)
            playback.play_pcm(pcm_bytes, sample_rate=sample_rate)
            return

    except Exception as e:
        log.warning("[TTS] TTS provider error (%s); falling back to system speech.", e)

    # Fallback to Windows built-in voice
    _play_fallback_voice(clean_text)


def _init_wakeword_model() -> OWWModel | None:
    """Initialize OpenWakeWord neural model for accurate 'Hey Jarvis' keyword spotting."""
    if not OWW_AVAILABLE:
        log.warning("openwakeword is not available; wake-word recognition disabled.")
        return None
    try:
        log.info("Initializing OpenWakeWord neural model ('hey_jarvis')...")
        openwakeword.utils.download_models()
        model = OWWModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        log.info("OpenWakeWord model ready (keyword: 'hey_jarvis', confidence threshold=%.2f).", WAKE_WORD_THRESHOLD)
        return model
    except Exception as e:
        log.error("Failed to initialize OpenWakeWord model: %s", e)
        return None




def say_jarvis_welcome() -> None:
    if not JARVIS_WELCOME_ENABLED or not JARVIS_WELCOME_PHRASE.strip():
        return
    say_jarvis_phrase(JARVIS_WELCOME_PHRASE)


def say_jarvis_goodbye() -> None:
    if not JARVIS_GOODBYE_ENABLED or not JARVIS_GOODBYE_PHRASE.strip():
        return
    say_jarvis_phrase(JARVIS_GOODBYE_PHRASE)


def play_song(uri: str) -> None:
    u = uri.strip()
    if not u:
        return
    try:
        if sys.platform == "win32":
            os.startfile(u)
        else:
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open SONG_URI: %s", e)


def _chrome_executable() -> str | None:
    if sys.platform == "win32":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("google-chrome") or shutil.which("chrome")


def _win32_sorted_monitor_rects() -> list[tuple[int, int, int, int]]:
    """Each monitor as (left, top, right, bottom), sorted left-to-right then top-to-bottom."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    collected: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
    def _cb(_hm, _hdc, lprc, _lp):
        r = lprc.contents
        collected.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, _cb, 0)
    collected.sort(key=lambda t: (t[0], t[1]))
    return collected


def _chrome_monitor_top_left(one_based_index: int) -> tuple[int, int]:
    """Top-left corner on virtual desktop for monitor N (1-based)."""
    l, t, _, _ = _chrome_monitor_bounds(one_based_index)
    return (l, t)


def _chrome_monitor_bounds(one_based_index: int) -> tuple[int, int, int, int]:
    """Monitor N as (left, top, right, bottom), 1-based index (sorted like other Chrome helpers)."""
    rects = _win32_sorted_monitor_rects()
    if not rects:
        return (0, 0, 1920, 1080)
    idx = one_based_index - 1
    if idx < 0:
        idx = 0
    if idx >= len(rects):
        log.warning(
            "Monitor %d requested but only %d found; using last monitor.",
            one_based_index,
            len(rects),
        )
        idx = len(rects) - 1
    return rects[idx]


def _chrome_monitor_pixel_size(one_based_index: int) -> tuple[int, int]:
    l, t, r, b = _chrome_monitor_bounds(one_based_index)
    return (max(320, r - l), max(240, b - t))


def _chrome_window_size() -> tuple[int, int]:
    w = (os.environ.get("CHROME_WINDOW_WIDTH") or "1400").strip()
    h = (os.environ.get("CHROME_WINDOW_HEIGHT") or "900").strip()
    try:
        return (max(400, int(w)), max(300, int(h)))
    except ValueError:
        return (1400, 900)


def _chrome_site_user_data_dir(site_key: str) -> str:
    p = Path(tempfile.gettempdir()) / "clap-trigger-chrome" / site_key
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _chrome_new_window_wait_timeout_s() -> float:
    try:
        return max(3.0, float((os.environ.get("CHROME_NEW_WINDOW_WAIT_S") or "25").strip()))
    except ValueError:
        return 25.0


def _chrome_top_level_browser_hwnds_win32() -> set[int]:
    """HWND ints for visible-or-minimized top-level Chrome browser windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    found: set[int] = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "chrome.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 80 or h < 80:
            return True
        found.add(int(hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def _wait_new_chrome_hwnd_win32(before: set[int], timeout: float) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.12)
        now = _chrome_top_level_browser_hwnds_win32()
        new = now - before
        if not new:
            continue
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        best: int | None = None
        best_area = 0
        for h in new:
            r = wintypes.RECT()
            if user32.GetWindowRect(h, ctypes.byref(r)):
                a = max(0, r.right - r.left) * max(0, r.bottom - r.top)
                if a > best_area:
                    best_area = a
                    best = h
        if best is not None:
            return best
    return None


def _chrome_snap_window_to_monitor_win32(
    hwnd: int,
    one_based_monitor: int,
    *,
    fullscreen: bool,
    windowed_size: tuple[int, int] | None,
) -> None:
    import ctypes
    from ctypes import wintypes

    ml, mt, mr, mb = _chrome_monitor_bounds(one_based_monitor)
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    SW_SHOWMAXIMIZED = 3
    HWND_TOP = 0
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED

    user32.ShowWindow(hwnd, SW_RESTORE)
    if fullscreen:
        w, h = mr - ml, mb - mt
        x, y = ml, mt
    else:
        ww, wh = windowed_size or _chrome_window_size()
        w, h = ww, wh
        x = ml + max(0, (mr - ml - w) // 2)
        y = mt + max(0, (mb - mt - h) // 2)
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, flags)

    if fullscreen:
        user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
        KEYEVENTF_KEYUP = 0x0002
        VK_F11 = 0x7A
        fg = user32.GetForegroundWindow()
        tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, True)
        user32.SetForegroundWindow(hwnd)
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, False)
        user32.keybd_event(VK_F11, 0, 0, 0)
        user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _open_url_in_chrome(
    url: str,
    *,
    new_window: bool = True,
    label: str = "URL",
    window_position: tuple[int, int] | None = None,
    window_size: tuple[int, int] | None = None,
    fullscreen: bool = False,
    win32_post_fullscreen_monitor: int | None = None,
    user_data_dir: str | None = None,
) -> None:
    u = url.strip()
    if not u:
        return
    chrome = _chrome_executable()
    try:
        if chrome:
            args = [chrome]
            if user_data_dir:
                args.append(f"--user-data-dir={user_data_dir}")
                args.append("--no-first-run")
            if new_window:
                args.append("--new-window")
            if window_position is not None:
                x, y = window_position
                args.append(f"--window-position={x},{y}")
            if window_size:
                args.append(f"--window-size={window_size[0]},{window_size[1]}")
            if fullscreen and not (
                sys.platform == "win32" and win32_post_fullscreen_monitor is not None
            ):
                args.append("--start-fullscreen")
            args.append(u)
            popen_kw: dict = {
                "args": args,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            before: set[int] | None = None
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                before = _chrome_top_level_browser_hwnds_win32()
            subprocess.Popen(**popen_kw)
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                mon = win32_post_fullscreen_monitor
                hwnd = _wait_new_chrome_hwnd_win32(before, _chrome_new_window_wait_timeout_s())
                if hwnd is not None:
                    _chrome_snap_window_to_monitor_win32(
                        hwnd,
                        mon,
                        fullscreen=fullscreen,
                        windowed_size=window_size if not fullscreen else None,
                    )
                else:
                    log.warning(
                        "Chrome: timed out waiting for new window (%s); check "
                        "CHROME_NEW_WINDOW_WAIT_S or close extra Chrome instances.",
                        label,
                    )
        else:
            log.warning("Chrome not found; opening %s in default browser.", label)
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open %s in Chrome: %s", label, e)


# --- Commented out per user request: Claude & Binance openers ---
# def open_claude_in_chrome() -> None:
#     if not OPEN_CLAUDE_CODE_IN_CHROME:
#         return
#     url = (os.environ.get("CLAUDE_CODE_URL") or "https://claude.ai/new").strip()
#     pos: tuple[int, int] | None = None
#     size: tuple[int, int] | None = None
#     fs = OPEN_CHROME_FULLSCREEN
#     post_mon: int | None = None
#     user_data: str | None = None
#     if sys.platform == "win32":
#         post_mon = CLAUDE_CHROME_MONITOR
#         pos = _chrome_monitor_top_left(CLAUDE_CHROME_MONITOR)
#         if fs:
#             size = _chrome_monitor_pixel_size(CLAUDE_CHROME_MONITOR)
#         else:
#             size = _chrome_window_size()
#         if CHROME_SEPARATE_SITE_PROFILES:
#             user_data = _chrome_site_user_data_dir("claude")
#     elif not fs:
#         size = _chrome_window_size()
#     else:
#         size = None
#     _open_url_in_chrome(
#         url,
#         new_window=True,
#         label="Claude",
#         window_position=pos,
#         window_size=size,
#         fullscreen=fs,
#         win32_post_fullscreen_monitor=post_mon,
#         user_data_dir=user_data,
#     )
# 
# 
# def open_binance_btc_in_chrome() -> None:
#     if not OPEN_BINANCE_BTC_IN_CHROME:
#         return
#     url = (
#         os.environ.get("BINANCE_BTC_URL")
#         or "https://www.binance.com/en/trade/BTC_USDT"
#     ).strip()
#     pos: tuple[int, int] | None = None
#     size: tuple[int, int] | None = None
#     fs = OPEN_CHROME_FULLSCREEN
#     post_mon: int | None = None
#     user_data: str | None = None
#     if sys.platform == "win32":
#         post_mon = BINANCE_CHROME_MONITOR
#         pos = _chrome_monitor_top_left(BINANCE_CHROME_MONITOR)
#         if fs:
#             size = _chrome_monitor_pixel_size(BINANCE_CHROME_MONITOR)
#         else:
#             size = _chrome_window_size()
#         if CHROME_SEPARATE_SITE_PROFILES:
#             user_data = _chrome_site_user_data_dir("binance")
#     elif not fs:
#         size = _chrome_window_size()
#     else:
#         size = None
#     _open_url_in_chrome(
#         url,
#         new_window=True,
#         label="Binance BTC",
#         window_position=pos,
#         window_size=size,
#         fullscreen=fs,
#         win32_post_fullscreen_monitor=post_mon,
#         user_data_dir=user_data,
#     )


def open_chrome_browser() -> None:
    """Open a new Google Chrome window."""
    if not OPEN_CHROME_ON_DOUBLE_CLAP:
        return
    chrome = _chrome_executable()
    if chrome:
        popen_kw: dict = {
            "args": [chrome, "--new-window"],
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            subprocess.Popen(**popen_kw)
            log.info("Opened Google Chrome.")
        except OSError as e:
            log.warning("Could not open Chrome: %s", e)
    else:
        log.warning("Chrome not found; opening default browser.")
        webbrowser.open("https://google.com")


def open_github_in_chrome() -> None:
    """Open GitHub in Chrome or default browser."""
    if not OPEN_GITHUB_IN_CHROME:
        return
    url = (os.environ.get("GITHUB_URL") or GITHUB_URL).strip()
    _open_url_in_chrome(url, new_window=True, label="GitHub")
    log.info("Opened GitHub: %s", url)


def _vscode_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for sub in (
            "Programs\\Microsoft VS Code\\Code.exe",
            "Programs\\Microsoft VS Code\\bin\\code.cmd",
        ):
            if local:
                p = os.path.join(local, *sub.split("\\"))
                if os.path.isfile(p):
                    return p
        for pf in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            if pf:
                p = os.path.join(pf, "Microsoft VS Code", "Code.exe")
                if os.path.isfile(p):
                    return p
    return shutil.which("code")


def _vscode_largest_main_hwnd_win32() -> int | None:
    """Largest top-level Code.exe window (visible or minimized)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    candidates: list[tuple[int, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "code.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 200 or h < 200:
            return True
        candidates.append((w * h, hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return None
    return int(max(candidates, key=lambda t: t[0])[1])


def _focus_existing_vscode_window_win32() -> bool:
    """Bring an existing Code.exe main window to the foreground (no new process)."""
    if sys.platform != "win32":
        return False
    hwnd = _vscode_largest_main_hwnd_win32()
    if hwnd is None:
        return False
    _cursor_foreground_hwnd_win32(hwnd)
    return True


def open_vscode_window() -> None:
    """Open or focus Visual Studio Code."""
    if not OPEN_VSCODE_ON_DOUBLE_CLAP:
        return
    exe = _vscode_executable()
    if not exe:
        log.warning(
            "Could not find VS Code (install app or add `code` to PATH)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        if FOCUS_EXISTING_VSCODE_ON_DOUBLE_CLAP:
            focused = (
                sys.platform == "win32" and _focus_existing_vscode_window_win32()
            )
            if not focused:
                subprocess.Popen([exe], **popen_kw)
        else:
            subprocess.Popen([exe], **popen_kw)
        log.info("Opened/focused VS Code.")
    except OSError as e:
        log.warning("Could not start or focus VS Code: %s", e)


def _antigravity_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for sub in (
            "Programs\\antigravity\\Antigravity.exe",
            "Programs\\Antigravity\\Antigravity.exe",
        ):
            if local:
                p = os.path.join(local, *sub.split("\\"))
                if os.path.isfile(p):
                    return p
        for pf in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            if pf:
                for sub in ("antigravity\\Antigravity.exe", "Antigravity\\Antigravity.exe"):
                    p = os.path.join(pf, *sub.split("\\"))
                    if os.path.isfile(p):
                        return p
    return shutil.which("antigravity") or shutil.which("gravity")


def open_antigravity_window() -> None:
    """Open Antigravity."""
    if not OPEN_ANTIGRAVITY_ON_DOUBLE_CLAP:
        return
    exe = _antigravity_executable()
    if not exe:
        log.warning(
            "Could not find Antigravity (install app or verify path)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen([exe], **popen_kw)
        log.info("Opened Antigravity.")
    except OSError as e:
        log.warning("Could not start Antigravity: %s", e)


def _get_screen_work_area() -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of primary monitor work area (excluding taskbar)."""
    if sys.platform != "win32":
        return (0, 0, 1920, 1080)
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    SPI_GETWORKAREA = 0x0030
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    return (0, 0, 1920, 1080)


def _calculate_layout_slots(mode: str, count: int) -> list[tuple[int, int, int, int]]:
    """Return list of (x, y, width, height) bounding boxes for each slot on the screen."""
    l, t, r, b = _get_screen_work_area()
    w = max(400, r - l)
    h = max(300, b - t)

    m = (os.environ.get("JARVIS_LAYOUT_MODE") or mode or "auto").strip().lower()

    if m == "auto":
        if count <= 1:
            m = "1_full"
        elif count == 2:
            m = "2_split"
        elif count == 3:
            m = "3_split"
        else:
            m = "4_split"

    if m in ("2_split", "split_2", "half"):
        half_w = w // 2
        return [
            (l, t, half_w, h),                    # Left 50%
            (l + half_w, t, w - half_w, h),       # Right 50%
        ]
    elif m in ("3_split", "split_3", "1_left_2_right"):
        half_w = w // 2
        half_h = h // 2
        return [
            (l, t, half_w, h),                    # Left 50% (Full height)
            (l + half_w, t, w - half_w, half_h),  # Top-Right (50% x 50%)
            (l + half_w, t + half_h, w - half_w, h - half_h), # Bottom-Right (50% x 50%)
        ]
    elif m in ("3_columns", "columns_3"):
        col_w = w // 3
        return [
            (l, t, col_w, h),
            (l + col_w, t, col_w, h),
            (l + 2 * col_w, t, w - 2 * col_w, h),
        ]
    elif m in ("4_split", "split_4", "grid_2x2", "quad"):
        half_w = w // 2
        half_h = h // 2
        return [
            (l, t, half_w, half_h),                    # Top-Left
            (l + half_w, t, w - half_w, half_h),       # Top-Right
            (l, t + half_h, half_w, h - half_h),       # Bottom-Left
            (l + half_w, t + half_h, w - half_w, h - half_h), # Bottom-Right
        ]
    return [(l, t, w, h)]


def _snap_window(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    """Move and resize window to given rect."""
    if sys.platform != "win32":
        return
    import ctypes
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    HWND_TOP = 0
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, SWP_SHOWWINDOW | SWP_FRAMECHANGED)


def _antigravity_largest_main_hwnd_win32() -> int | None:
    """Largest top-level Antigravity.exe window."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    candidates: list[tuple[int, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "antigravity.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 200 or h < 200:
            return True
        candidates.append((w * h, hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return None
    return int(max(candidates, key=lambda t: t[0])[1])


def arrange_opened_windows(mode: str | None = None) -> None:
    """Collect HWNDs of opened apps and tile them according to layout mode."""
    if sys.platform != "win32":
        return
    layout = mode or LAYOUT_MODE
    if layout == "none":
        return

    # Calculate expected number of windows
    expected = 0
    if OPEN_VSCODE_ON_DOUBLE_CLAP:
        expected += 1
    if OPEN_ANTIGRAVITY_ON_DOUBLE_CLAP:
        expected += 1
    if OPEN_CHROME_ON_DOUBLE_CLAP:
        expected += 1
    if OPEN_GITHUB_IN_CHROME:
        expected += 1
    if expected < 2:
        expected = 2

    # Give windows a moment to initialize
    try:
        delay = float((os.environ.get("JARVIS_LAYOUT_DELAY_S") or str(LAYOUT_DELAY_S)).strip())
    except ValueError:
        delay = 1.5

    # Initial delay for apps to start creating windows
    time.sleep(delay)

    # Poll for windows to appear
    deadline = time.monotonic() + 4.0
    app_hwnds: list[tuple[str, int]] = []

    while time.monotonic() < deadline:
        app_hwnds = []

        if OPEN_VSCODE_ON_DOUBLE_CLAP:
            vs_hwnd = _vscode_largest_main_hwnd_win32()
            if vs_hwnd:
                app_hwnds.append(("VS Code", vs_hwnd))

        if OPEN_ANTIGRAVITY_ON_DOUBLE_CLAP:
            anti_hwnd = _antigravity_largest_main_hwnd_win32()
            if anti_hwnd:
                app_hwnds.append(("Antigravity", anti_hwnd))

        if OPEN_CHROME_ON_DOUBLE_CLAP or OPEN_GITHUB_IN_CHROME:
            chrome_hwnds = sorted(list(_chrome_top_level_browser_hwnds_win32()))
            for idx, ch_hwnd in enumerate(chrome_hwnds):
                label = "GitHub" if idx == 1 else "Chrome"
                app_hwnds.append((label, ch_hwnd))

        # Check if we have collected all expected windows
        if len(app_hwnds) >= expected:
            break
        time.sleep(0.4)

    if not app_hwnds:
        return

    slots = _calculate_layout_slots(layout, len(app_hwnds))
    if not slots:
        return

    log.info("Arranging %d windows with layout '%s' into %d slots...", len(app_hwnds), layout, len(slots))
    for i, (name, hwnd) in enumerate(app_hwnds):
        if i < len(slots):
            x, y, w, h = slots[i]
            _snap_window(hwnd, x, y, w, h)
            log.info("Snapped %s into slot %d: (x=%d, y=%d, w=%d, h=%d)", name, i+1, x, y, w, h)


def _cursor_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for sub in ("Programs\\cursor\\Cursor.exe", "Programs\\Cursor\\Cursor.exe"):
            if local:
                p = os.path.join(local, *sub.split("\\"))
                if os.path.isfile(p):
                    return p
    return shutil.which("cursor")


def _cursor_largest_main_hwnd_win32() -> int | None:
    """Largest top-level Cursor.exe window (visible or minimized)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    candidates: list[tuple[int, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "cursor.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 200 or h < 200:
            return True
        candidates.append((w * h, hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return None
    return int(max(candidates, key=lambda t: t[0])[1])


def _cursor_foreground_hwnd_win32(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, True)
    user32.SetForegroundWindow(hwnd)
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, False)


def _cursor_send_f11_fullscreen_win32(hwnd: int) -> None:
    """F11 toggles Zen/fullscreen in Cursor (Electron)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_F11 = 0x7A
    _cursor_foreground_hwnd_win32(hwnd)
    user32.keybd_event(VK_F11, 0, 0, 0)
    user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _focus_existing_cursor_window_win32() -> bool:
    """Bring an existing Cursor.exe main window to the foreground (no new process)."""
    if sys.platform != "win32":
        return False
    hwnd = _cursor_largest_main_hwnd_win32()
    if hwnd is None:
        return False
    _cursor_foreground_hwnd_win32(hwnd)
    return True


def run_double_clap_actions() -> None:
    """Run outside the mic loop so sleeps do not stall capture."""
    bridge.set_state("processing")

    # Load custom workspace configuration
    config_path = os.path.join(os.path.dirname(__file__), "config", "workspace_config.json")
    actions_executed = 0
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            actions = config.get("double_clap_actions", [])
            for action in actions:
                action_type = action.get("type")
                target = action.get("target")
                if action_type == "app" and target:
                    ToolRegistry.get_instance().execute("open_application", app_name=target)
                    time.sleep(0.2)
                    actions_executed += 1
                elif action_type == "url" and target:
                    ToolRegistry.get_instance().execute("open_url", url=target, new_window=False)
                    time.sleep(0.2)
                    actions_executed += 1
        except Exception as e:
            log.error("Failed to execute workspace config: %s", e)
    
    # Fallback to hardcoded defaults if config empty or missing
    if actions_executed == 0:
        open_vscode_window()
        time.sleep(0.2)
        open_antigravity_window()
        time.sleep(0.2)
        open_chrome_browser()
        time.sleep(0.3)
        open_github_in_chrome()
    play_song(SONG_URI)

    # Automatically split/arrange windows on screen (4 slots)
    if LAYOUT_MODE != "none":
        threading.Thread(target=arrange_opened_windows, daemon=True).start()

    if JARVIS_WELCOME_ENABLED and JARVIS_WELCOME_PHRASE.strip():
        delay = max(0.0, JARVIS_AFTER_SONG_DELAY_S)
        if delay:
            time.sleep(delay)
        threading.Thread(target=say_jarvis_welcome, daemon=True).start()
    else:
        bridge.set_state("listening")
    open_cursor_window()


def close_all_target_processes() -> None:
    """Close/kill running target applications."""
    if sys.platform == "win32":
        for proc in CLOSE_PROCESS_NAMES:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                log.info("Closed process: %s", proc)
            except Exception as e:
                log.warning("Could not close %s: %s", proc, e)
    else:
        for proc in ("code", "antigravity", "chrome", "spotify", "cursor"):
            subprocess.run(["pkill", "-f", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def shutdown_computer(delay_s: int = 3) -> None:
    """Initiate Windows / system shutdown."""
    log.info("Executing system shutdown in %d seconds...", delay_s)
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["shutdown", "/s", "/f", "/t", str(max(0, delay_s))],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.Popen(["shutdown", "-h", "now"])
    except Exception as e:
        log.error("Failed to trigger shutdown: %s", e)


def show_shutdown_countdown_dialog(timeout_s: int = 6) -> bool:
    """Show an always-on-top modal countdown window with a Cancel button.

    Returns True if countdown expired (proceed to shutdown), or False if user canceled.
    """
    import tkinter as tk

    canceled = False
    confirmed = False
    remaining = max(1, timeout_s)

    try:
        root = tk.Tk()
        root.title("Jarvis - Xác nhận Tắt Máy")
        root.geometry("450x250")
        root.configure(bg="#1e1e2e")
        root.attributes("-topmost", True)
        root.resizable(False, False)

        # Center dialog on screen
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - 450) // 2)
        y = max(0, (sh - 250) // 2)
        root.geometry(f"450x250+{x}+{y}")

        title_lbl = tk.Label(
            root,
            text=" Jarvis: Nhận diện 3 tiếng vỗ tay",
            font=("Segoe UI", 13, "bold"),
            fg="#f38ba8",
            bg="#1e1e2e",
        )
        title_lbl.pack(pady=(16, 4))

        sub_lbl = tk.Label(
            root,
            text="Hệ thống sẽ đóng các ứng dụng và tắt máy sau:",
            font=("Segoe UI", 10),
            fg="#cdd6f4",
            bg="#1e1e2e",
        )
        sub_lbl.pack(pady=(0, 6))

        time_lbl = tk.Label(
            root,
            text=f"{remaining} giây",
            font=("Segoe UI", 26, "bold"),
            fg="#fab387",
            bg="#1e1e2e",
        )
        time_lbl.pack(pady=(0, 10))

        def on_cancel():
            nonlocal canceled
            canceled = True
            root.destroy()

        btn_cancel = tk.Button(
            root,
            text="CANCEL",
            font=("Segoe UI", 11, "bold"),
            bg="#24d8f0",
            fg="#11111b",
            activebackground="#94e2d5",
            activeforeground="#11111b",
            padx=24,
            pady=8,
            relief="flat",
            cursor="hand2",
            command=on_cancel,
        )
        btn_cancel.pack()

        # Keyboard shortcuts to cancel
        root.bind("<Escape>", lambda e: on_cancel())
        root.bind("<space>", lambda e: on_cancel())
        root.protocol("WM_DELETE_WINDOW", on_cancel)

        def tick():
            nonlocal remaining, confirmed
            if canceled:
                return
            remaining -= 1
            if remaining <= 0:
                confirmed = True
                root.destroy()
            else:
                time_lbl.config(text=f"{remaining} giây")
                root.after(1000, tick)

        root.after(1000, tick)
        root.mainloop()
    except Exception as e:
        log.warning("Could not show countdown GUI: %s. Falling back to console countdown.", e)
        time.sleep(timeout_s)
        return True

    return confirmed and not canceled


def run_triple_clap_actions() -> None:
    """Run on triple clap: show 6s countdown, and if not canceled, close apps and shut down PC."""
    bridge.set_state("processing")
    log.info(
        "TRIPLE CLAP ACTION: 3 claps detected! Showing %ds cancelable countdown...",
        SHUTDOWN_COUNTDOWN_S,
    )

    # Optional: play warning audio in background
    if JARVIS_GOODBYE_ENABLED and JARVIS_GOODBYE_PHRASE.strip():
        threading.Thread(
            target=say_jarvis_phrase,
            args=("Shutting down system in 6 seconds. Press cancel to abort.",),
            daemon=True,
        ).start()

    # Show 6-second countdown dialog with Cancel button
    proceed = show_shutdown_countdown_dialog(timeout_s=SHUTDOWN_COUNTDOWN_S)

    if not proceed:
        log.info("SHUTDOWN CANCELED by user. No applications were closed.")
        bridge.set_state("listening")
        return

    log.info("Shutdown confirmed. Closing applications and shutting down PC now...")

    # 1. Close all target processes
    close_all_target_processes()

    # 2. Say goodbye phrase
    if JARVIS_GOODBYE_ENABLED and JARVIS_GOODBYE_PHRASE.strip():
        try:
            say_jarvis_goodbye()
        except Exception as e:
            log.warning("Could not play goodbye: %s", e)

    # 3. Shutdown Windows immediately
    shutdown_computer(delay_s=SHUTDOWN_DELAY_S)


def open_cursor_window() -> None:
    if not FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP and not OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
        return
    exe = _cursor_executable()
    if not exe:
        log.warning(
            "Could not find Cursor (install app or add the `cursor` command to PATH)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        if FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP:
            focused = (
                sys.platform == "win32" and _focus_existing_cursor_window_win32()
            )
            if not focused:
                subprocess.Popen([exe], **popen_kw)
        if OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
            subprocess.Popen([exe, "-n"], **popen_kw)
    except OSError as e:
        log.warning("Could not start or focus Cursor: %s", e)
        return
    if sys.platform == "win32" and CURSOR_OPEN_FULLSCREEN:
        time.sleep(0.5)
        hwnd = _cursor_largest_main_hwnd_win32()
        if hwnd is not None:
            _cursor_send_f11_fullscreen_win32(hwnd)
        else:
            log.warning("Cursor fullscreen: no Cursor window found to send F11.")


class JarvisCoordinator:
    """
    Central Jarvis Runtime Coordinator:
    - Owns and coordinates single microphone pipeline via AudioManager
    - Manages VAD & speech boundary detection
    - Handles TRIGGER Mode (deterministic claps & quick commands)
    - Handles CHAT Mode (conversational voice, intent routing, and Hermes Agent Computer Use)
    - Enforces strict mutual exclusion and clean resource recovery
    """

    def __init__(self, audio_mgr: AudioManager, blocksize: int):
        self.audio_mgr = audio_mgr
        self.blocksize = blocksize
        self.vad = AudioVAD(sample_rate=SAMPLE_RATE)
        self.hermes_client = HermesClient()
        self.current_chat_session_id: str | None = None
        self._agent_busy = False
        self._agent_lock = threading.Lock()
        self._turn_in_flight = False
        self._turn_lock = threading.Lock()
        self._chat_turn_text: list[str] = []
        self._chat_turn_pcm: list[bytes] = []
        self._last_speech_time: float = 0.0
        self._user_is_speaking: bool = False

        self.spike_armed = True
        self.calibrated = False
        self.stream_start_time = 0.0

        self.last_action_time = 0.0
        self.clap_times: list[float] = []
        self.recent_burst_hits: list[float] = []
        self.typing_suppress_until = 0.0
        self.welcome_sequence_done = False

        self.wake_armed_until = 0.0
        self.last_wake_trigger = 0.0
        self.wake_window_expired_logged = True
        self._last_vosk_reset = 0.0

        self.oww_model: OWWModel | None = None
        if REQUIRE_WAKE_WORD:
            self.oww_model = _init_wakeword_model()

        self.vosk_recognizer = None
        self._vosk_lock = threading.Lock()
        if VOSK_AVAILABLE and vosk_model is not None:
            try:
                self.vosk_recognizer = vosk.KaldiRecognizer(vosk_model, SAMPLE_RATE)
            except Exception as e:
                log.warning("Could not initialize Vosk recognizer: %s", e)

    def _safe_reset_vosk(self) -> None:
        """Thread-safe reset of Vosk recognizer state."""
        if self.vosk_recognizer is not None:
            try:
                with self._vosk_lock:
                    self.vosk_recognizer.Reset()
            except Exception:
                pass

    # -------------------------------------------------------------
    # TRIGGER MODE LISTENER (Microphone Owner: TRIGGER)
    # -------------------------------------------------------------
    def process_trigger_frame(self, data: np.ndarray, now: float) -> None:
        level = AudioManager.calculate_rms(data)
        threshold = max(self.audio_mgr.noise_floor * SPIKE_RATIO, MIN_RMS)

        # Startup Warmup & Calibration
        if not self.calibrated:
            if (now - self.stream_start_time) < STARTUP_WARMUP_S:
                self.clap_times = []
                self.recent_burst_hits = []
                self.spike_armed = False
                return
            self.calibrated = True
            self.spike_armed = True
            log.info(
                "Microphone calibration complete (baseline noise=%.5f, threshold=%.5f). Ready for commands!",
                self.audio_mgr.noise_floor,
                threshold,
            )
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
                except Exception:
                    pass
            if REQUIRE_WAKE_WORD and self.oww_model is not None:
                log.info("Say 'Hey Jarvis, I need your help' for Conversation mode, or clap for Commands.")

        # Re-trigger level for claps
        if level < threshold * RETRIGGER_RATIO:
            self.spike_armed = True

        # Ignore incoming audio if Jarvis is currently speaking / playing audio
        if self.audio_mgr.is_speaking(now) or (now < JARVIS_SPEAKING_UNTIL):
            return

        pcm_bytes = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

        # A. Neural OpenWakeWord detection
        if REQUIRE_WAKE_WORD and self.oww_model is not None:
            pcm_i16 = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16).flatten()
            prediction = self.oww_model.predict(pcm_i16)
            score = prediction.get("hey_jarvis", 0.0)

            if score >= WAKE_WORD_THRESHOLD and (now - self.last_wake_trigger) > 4.0:
                self.last_wake_trigger = now
                self.wake_armed_until = now + WAKE_WINDOW_S
                self.wake_window_expired_logged = False
                self.clap_times = []
                self._safe_reset_vosk()
                log.info(
                    "🎙️ [WAKE DETECTED]: 'Hey Jarvis'! (confidence=%.2f >= %.2f) — Listening for commands / claps...",
                    score,
                    WAKE_WORD_THRESHOLD,
                )
                if WAKE_FEEDBACK_ENABLED:
                    threading.Thread(
                        target=say_jarvis_phrase,
                        args=("Yes sir?",),
                        daemon=True
                    ).start()

        # B. Vosk Streaming Speech & Intent Routing (Waiting Mode)
        if self.vosk_recognizer is not None:
            text = ""
            try:
                # Sensitive gate: Feed Vosk whenever audio is slightly above baseline noise floor
                vosk_gate = max(self.audio_mgr.noise_floor * 1.3, 0.0005)
                if level >= vosk_gate:
                    with self._vosk_lock:
                        if self.vosk_recognizer.AcceptWaveform(pcm_bytes):
                            res = json.loads(self.vosk_recognizer.Result())
                            text = res.get("text", "").lower().strip()
                        else:
                            res = json.loads(self.vosk_recognizer.PartialResult())
                            text = res.get("partial", "").lower().strip()
                elif (now - self._last_vosk_reset) > 2.0:
                    self._last_vosk_reset = now
                    self._safe_reset_vosk()
            except Exception:
                text = ""

            if text:
                # Suppress clap detection for 1.2s if any speech is recognized
                self.typing_suppress_until = now + 1.2
                self.clap_times = []
                self._route_waiting_intent(text, now)

        # C. Clap Sequence Detection (Command Mode)
        self._handle_claps(level, threshold, now)

    def _route_waiting_intent(self, text: str, now: float) -> None:
        # Ignore sleep phrases in waiting mode
        sleep_phrases = ("go to sleep", "to sleep", "sleep", "close", "dismiss", "turn off", "shut down", "goodbye", "bye")
        if any(sp in text for sp in sleep_phrases):
            self._safe_reset_vosk()
            return

        # Dedicated Conversation Activation Phrase: "Jarvis, I need your help" / "Jarvis ơi"
        conv_phrases = (
            "i need your help", "need your help", "need help", "help me",
            "jarvis oi", "jarvis ơi", "goi jarvis", "gọi jarvis", "tro chuyen", "trò chuyện",
            "giup toi", "giúp tôi", "and it your hair", "a nice your hair", "it your hair",
            "start conversation", "open jarvis", "wake up", "i need help"
        )
        is_conv_transition = any(cp in text for cp in conv_phrases) or (
            self.wake_armed_until > now and any(k in text for k in ("help", "need", "tro chuyen", "trò chuyện", "jarvis", "chavis", "ơi", "oi"))
        )
        if is_conv_transition:
            log.info("🌟 [INTENT: CONVERSATION] Dedicated phrase detected ('%s') -> Materializing Jarvis Orb...", text)
            self._safe_reset_vosk()
            self.wake_armed_until = 0.0
            self.clap_times = []

            # 1. Acquire Chat session in bridge
            session_id = bridge.emit_wake()
            self.current_chat_session_id = session_id
            log.info("[JARVIS] Conversation session acquired. ID: %s", session_id)

            # 2. Acquire audio ownership for CHAT mode
            self.audio_mgr.acquire(AudioOwner.CHAT)

            # 3. Start Hermes session in background
            def _init_chat():
                try:
                    asyncio.run(self.hermes_client.start_session(session_id))
                except Exception as e:
                    log.warning("[HERMES] Could not pre-init session: %s", e)
                say_jarvis_phrase("Yes sir, I am online and ready to help.")

            threading.Thread(target=_init_chat, daemon=True).start()
            return

        # Direct Voice Commands in Waiting Mode
        if "open spotify" in text or "play music" in text or "play song" in text:
            log.info("🎵 [INTENT: COMMAND] 'Open Spotify' -> Executing command (UI remains hidden)...")
            self._safe_reset_vosk()
            self.wake_armed_until = 0.0
            play_song(SONG_URI)
            threading.Thread(target=say_jarvis_phrase, args=("Opening Spotify.",), daemon=True).start()
            return

        if "open vs code" in text or "open vscode" in text or "open code" in text:
            log.info("💻 [INTENT: COMMAND] 'Open VS Code' -> Executing command (UI remains hidden)...")
            self._safe_reset_vosk()
            self.wake_armed_until = 0.0
            open_vscode_window()
            threading.Thread(target=say_jarvis_phrase, args=("Opening Visual Studio Code.",), daemon=True).start()
            return

        if "open chrome" in text:
            log.info("🌐 [INTENT: COMMAND] 'Open Chrome' -> Executing command (UI remains hidden)...")
            self._safe_reset_vosk()
            self.wake_armed_until = 0.0
            open_chrome_browser()
            threading.Thread(target=say_jarvis_phrase, args=("Opening Chrome.",), daemon=True).start()
            return

        if "open browser" in text or "mở trình duyệt" in text:
            log.info("🌐 [INTENT: COMMAND] 'Open Browser' -> Executing command (UI remains hidden)...")
            self._safe_reset_vosk()
            self.wake_armed_until = 0.0
            import os
            threading.Thread(target=os.startfile, args=("https://www.google.com",), daemon=True).start()
            threading.Thread(target=say_jarvis_phrase, args=("Opening default browser.",), daemon=True).start()
            return

    def _handle_claps(self, level: float, threshold: float, now: float) -> None:
        # Check wake-word window timeout
        if REQUIRE_WAKE_WORD and self.oww_model is not None:
            if self.wake_armed_until > 0.0 and now > self.wake_armed_until:
                self.wake_armed_until = 0.0
                self.clap_times = []
                if not self.wake_window_expired_logged:
                    self.wake_window_expired_logged = True
                    log.info("⏳ Wake window expired (%.1fs). Returning to waiting mode...", WAKE_WINDOW_S)

        # Clean burst hits
        self.recent_burst_hits = [t for t in self.recent_burst_hits if (now - t) <= BURST_WINDOW_S]
        if len(self.recent_burst_hits) > MAX_BURST_HITS:
            self.clap_times = []
            self.typing_suppress_until = now + 0.6

        # Check 2-clap timeout
        if len(self.clap_times) == 2 and (now - self.clap_times[-1]) > MAX_CLAP_GAP_S:
            gap = self.clap_times[1] - self.clap_times[0]
            self.clap_times = []
            self.last_action_time = now
            self.wake_armed_until = 0.0
            if not self.welcome_sequence_done:
                self.welcome_sequence_done = True
                log.info("✅ 2 CLAPS DETECTED (gap=%.3fs) -> Running workspace setup actions...", gap)
                threading.Thread(target=run_double_clap_actions, daemon=True).start()
        elif len(self.clap_times) == 1 and (now - self.clap_times[0]) > MAX_CLAP_GAP_S:
            self.clap_times = []

        # Detect spike
        if (
            self.spike_armed
            and level >= threshold
            and (now - self.last_action_time) >= COOLDOWN_S
        ):
            self.spike_armed = False
            self.recent_burst_hits.append(now)
            if now < self.typing_suppress_until or len(self.recent_burst_hits) > MAX_BURST_HITS:
                self.clap_times = []
                return

            if REQUIRE_WAKE_WORD and self.oww_model is not None:
                if now > self.wake_armed_until:
                    return

            if not self.clap_times:
                self.clap_times = [now]
                log.info("👏 Clap hit [1] (rms=%.4f). Waiting for next clap...", level)
            else:
                gap = now - self.clap_times[-1]
                if gap < MIN_CLAP_GAP_S:
                    pass
                elif gap <= MAX_CLAP_GAP_S:
                    self.clap_times.append(now)
                    if len(self.clap_times) == 2:
                        log.info("👏 Clap hit [2]! Waiting %.2fs to distinguish 2 vs 3 claps...", MAX_CLAP_GAP_S)
                    elif len(self.clap_times) == 3:
                        log.info("🛑 3 CLAPS DETECTED! Initiating shutdown countdown...")
                        self.clap_times = []
                        self.last_action_time = now
                        self.wake_armed_until = 0.0
                        if TRIPLE_CLAP_ENABLED:
                            threading.Thread(target=run_triple_clap_actions, daemon=True).start()
                else:
                    self.clap_times = [now]
                    log.info("👏 Clap hit [1] (new sequence, rms=%.4f)!", level)

    # -------------------------------------------------------------
    # CHAT MODE LISTENER (Microphone Owner: CHAT)
    # -------------------------------------------------------------
    def process_chat_frame(self, data: np.ndarray, now: float) -> None:
        # Check if conversation session was ended or expired
        if not bridge.is_conversation_active():
            log.info("[CHAT] Conversation session inactive -> Releasing audio to TRIGGER mode.")
            self.audio_mgr.acquire(AudioOwner.TRIGGER)
            return

        # If agent is currently executing, Jarvis is speaking, or a turn is being processed, drop incoming mic frames
        if getattr(self, "_agent_busy", False) or getattr(self, "_turn_in_flight", False) or self.audio_mgr.is_speaking(now):
            if self._chat_turn_pcm or self._user_is_speaking:
                self._chat_turn_pcm.clear()
                self._user_is_speaking = False
                self.vad.reset()
            return

        level = AudioManager.calculate_rms(data)
        threshold = max(self.audio_mgr.noise_floor * SPIKE_RATIO, MIN_RMS)

        # Stream live audio amplitude to UI Orb when in listening state
        if bridge.current_state == "listening":
            norm_level = (level - self.audio_mgr.noise_floor) / max(threshold - self.audio_mgr.noise_floor, 1e-4)
            bridge.emit_audio_level(min(1.0, max(0.0, norm_level)))

        # VAD & Speech Activity Detection via Central Silero Neural VAD
        vad_evt, full_pcm = self.vad.feed(data)

        if vad_evt == "SPEECH_START":
            if not self._user_is_speaking:
                self._user_is_speaking = True
                log.info("🎙️ [VAD] User started speaking turn...")
            self._last_speech_time = now

        elif vad_evt == "SPEAKING":
            self._last_speech_time = now

        elif vad_evt == "SPEECH_END" and full_pcm:
            self._user_is_speaking = False
            self._safe_reset_vosk()

            # Guard: Require at least 0.60s of audio to reject brief mic clicks/background breath
            min_bytes = int(SAMPLE_RATE * 0.60 * 2)
            if len(full_pcm) < min_bytes:
                log.debug("[CHAT] Discarding short audio burst (%d bytes < %d bytes)", len(full_pcm), min_bytes)
                return

            with self._turn_lock:
                if self._turn_in_flight:
                    log.debug("[CHAT] Turn already in flight, skipping overlapping audio burst.")
                    return
                self._turn_in_flight = True

            threading.Thread(
                target=self._async_transcribe_and_handle,
                args=(full_pcm,),
                daemon=True,
            ).start()

    def _async_transcribe_and_handle(self, turn_pcm: bytes) -> None:
        """Asynchronously transcribe audio turn and dispatch utterance without blocking audio capture stream."""
        try:
            from agent.smart_stt import SmartSTT
            stt_res = SmartSTT.get_instance().transcribe_turn(
                turn_pcm,
                sample_rate=SAMPLE_RATE,
                session_context={"session_id": self.current_chat_session_id},
            )
            raw_turn = stt_res.text.strip()

            if raw_turn:
                # Run Voice Normalization & Semantic Interpretation Pipeline
                ctx = VoiceNormalizationPipeline.get_instance().process_transcript(raw_turn)
                log.info("🎙️ [SMART TURN COMPLETED] Raw: '%s' | Normalized: '%s'", ctx.raw_transcript, ctx.normalized_transcript)
                self._handle_chat_utterance(ctx.normalized_transcript or raw_turn, interpretation=ctx)
            else:
                if bridge.is_conversation_active():
                    bridge.set_state("listening")
        except Exception as e:
            log.error("[CHAT] Error in async transcription handler: %s", e, exc_info=True)
            if bridge.is_conversation_active():
                bridge.set_state("listening")
        finally:
            with self._turn_lock:
                self._turn_in_flight = False

    def _handle_chat_utterance(self, text: str, interpretation: InterpretationContext | None = None) -> None:
        # Capture current interactive window snapshot before Hermes reasoning or routing
        try:
            from agent.tools.window_target_resolver import WindowTargetResolver
            WindowTargetResolver.capture_foreground_snapshot()
        except Exception as e:
            log.debug("Window snapshot capture notice: %s", e)

        ctx = interpretation or VoiceNormalizationPipeline.get_instance().process_transcript(text)
        log.info("💬 [CONVERSATION MODE] Processing user command: '%s' (Raw STT: '%s')", text, ctx.raw_transcript)
        bridge.touch_session()

        # Language Detection & Invariant Verification
        from agent.language import LanguageDetector
        lang_type, lang_conf, _ = LanguageDetector.get_instance().detect(ctx.raw_transcript)

        # Structured diagnostic logs
        log.info("🎙️ [STT] raw = '%s'", ctx.raw_transcript)
        log.info("🌐 [LANGUAGE] detected = '%s' (confidence=%.2f, response_rule='ALWAYS_ENGLISH')", lang_type.value, lang_conf)
        log.info("✨ [NORMALIZER] normalized = '%s'", ctx.normalized_transcript)
        log.info("🎯 [INTENT] type = %s (confidence=%.2f, compound=%s)", ctx.intent, ctx.confidence, ctx.is_compound)
        if ctx.target_entity:
            log.info("🏷️ [ENTITY] candidate = '%s' (alias='%s', method=%s, confidence=%.2f)",
                     ctx.target_entity.name, ctx.target_entity.matched_alias,
                     ctx.target_entity.match_method, ctx.target_entity.confidence)

        target, action, meta = CommandRouter.route(ctx.raw_transcript, interpretation=ctx)
        log.info("[ROUTER] Command: '%s' -> Target: %s (Action: %s)", text, target.value, action)

        # 0. Ignore ambient noise / filler fragments
        if target == RouteTarget.IGNORE:
            log.info("[CHAT] Ignored noise/filler phrase: '%s'", text)
            self._safe_reset_vosk()
            return

        # 1. Sleep & Close Session
        if target == RouteTarget.SLEEP_DISMISS:
            log.info("🛑 [CONVERSATION CLOSE] User requested sleep ('%s') -> Closing session...", text)
            self._safe_reset_vosk()
            bridge.emit_closing()
            self.audio_mgr.acquire(AudioOwner.TRIGGER)

            if self.current_chat_session_id:
                try:
                    asyncio.run(self.hermes_client.close_session(self.current_chat_session_id))
                except Exception as e:
                    log.debug("Session close error: %s", e)
                self.current_chat_session_id = None

            if JARVIS_GOODBYE_ENABLED:
                threading.Thread(
                    target=say_jarvis_phrase,
                    args=("Going to sleep, sir.",),
                    daemon=True
                ).start()
            return

        # 2. Deterministic Action (Fast Path)
        elif target == RouteTarget.DETERMINISTIC_ACTION:
            self._safe_reset_vosk()
            bridge.set_state("processing")
            log.info("[ACTION] Fast-path executing deterministic action: %s", action)

            if action.startswith("open_app:"):
                app_name = ctx.target_entity.name if ctx.target_entity else action.split(":", 1)[1]
                log.info("[TOOL] open_application('%s')", app_name)
                res = ToolRegistry.get_instance().execute("open_application", app_name=app_name)
                log.info("[RESULT] %s", "success" if res.get("success") else f"failed: {res.get('error')}")
                say_jarvis_phrase(f"Opening {app_name}, sir.")
            elif action == "open_spotify":
                log.info("[TOOL] open_application('Spotify')")
                play_song(SONG_URI)
                log.info("[RESULT] success")
                say_jarvis_phrase("Spotify playback started, sir.")
            elif action == "open_vscode":
                log.info("[TOOL] open_application('Visual Studio Code')")
                open_vscode_window()
                log.info("[RESULT] success")
                say_jarvis_phrase("Visual Studio Code is ready.")
            elif action == "open_chrome":
                log.info("[TOOL] open_application('Google Chrome')")
                open_chrome_browser()
                log.info("[RESULT] success")
                say_jarvis_phrase("Google Chrome launched.")
            elif action == "open_antigravity":
                log.info("[TOOL] open_application('Antigravity')")
                open_antigravity_window()
                log.info("[RESULT] success")
                say_jarvis_phrase("Antigravity is active.")
            elif action == "open_cursor":
                log.info("[TOOL] open_application('Cursor')")
                open_cursor_window()
                log.info("[RESULT] success")
                say_jarvis_phrase("Cursor editor opened.")

            if bridge.is_conversation_active():
                bridge.set_state("listening")
                log.info("[CHAT] Returned to listening state. Ready for next voice command.")
            else:
                self.audio_mgr.acquire(AudioOwner.TRIGGER)
            return

        # 3. Hermes Agent Complex & Natural Language Task
        elif target == RouteTarget.HERMES_AGENT:
            self._safe_reset_vosk()

            session_id = self.current_chat_session_id or "default_session"
            log.info("🧠 [HERMES] Starting task delegation to Hermes Agent loop for session: %s", session_id)
            threading.Thread(
                target=self._run_hermes_agent_thread,
                args=(session_id, text, ctx),
                daemon=True,
            ).start()

    def _run_hermes_agent_thread(
        self,
        session_id: str,
        instruction: str,
        interpretation_context: InterpretationContext | None = None,
    ) -> None:
        """Execute Hermes Agent planning and computer use in a background worker thread."""
        with self._agent_lock:
            if getattr(self, "_agent_busy", False):
                log.warning("[HERMES] Another agent task is already active. Skipping duplicate instruction.")
                return
            self._agent_busy = True

        bridge.set_state("agent_thinking")
        log.info("[HERMES] Step 1: Agent thinking & reasoning about instruction '%s'...", instruction)

        def _on_agent_event(evt: AgentEvent):
            bridge.emit_agent_event(evt.event_type.value, evt.payload)
            if evt.event_type == EventType.AGENT_THINKING:
                log.info("[HERMES EVENT] 💭 Thinking: %s", evt.payload.get("status", ""))
                bridge.set_state("agent_thinking")
            elif evt.event_type in (EventType.AGENT_TOOL_STARTED, EventType.AGENT_TOOL_PROGRESS):
                log.info("[HERMES EVENT] ⚙️ Executing tool: '%s' (params: %s)", evt.payload.get("tool"), evt.payload.get("params"))
                bridge.set_state("agent_acting")
            elif evt.event_type == EventType.AGENT_TOOL_FINISHED:
                log.info("[HERMES EVENT] ✅ Tool finished: '%s' (result: %s)", evt.payload.get("tool"), evt.payload.get("result"))
            elif evt.event_type == EventType.AGENT_VERIFYING:
                log.info("[HERMES EVENT] 🔍 Verifying results: %s", evt.payload.get("status", ""))
                bridge.set_state("agent_verifying")
            elif evt.event_type == EventType.AGENT_COMPLETED:
                log.info("[HERMES EVENT] 🎯 Completed! Response: '%s'", evt.payload.get("response"))

        try:
            log.info("[CHAT -> HERMES] Dispatching instruction: '%s' (Intent: %s)",
                     instruction, interpretation_context.intent if interpretation_context else "None")
            response = asyncio.run(
                self.hermes_client.send_message(
                    session_id=session_id,
                    message=instruction,
                    event_callback=_on_agent_event,
                    interpretation_context=interpretation_context,
                )
            )

            log.info("[HERMES -> CHAT] Final response synthesized: '%s' (success=%s)", response.text, response.success)
            if response.text and response.text.strip():
                say_jarvis_phrase(response.text.strip())
            else:
                log.info("[HERMES] Response is silent (no speech synthesis needed).")

        except Exception as e:
            log.error("[HERMES ERROR] Failed executing instruction '%s': %s", instruction, e, exc_info=True)
            say_jarvis_phrase("I encountered an issue while carrying out that task, sir.")
        finally:
            with self._agent_lock:
                self._agent_busy = False
            if bridge.is_conversation_active():
                bridge.set_state("listening")
                log.info("[CHAT] Returned to listening state. Ready for next voice command.")
            else:
                self.audio_mgr.acquire(AudioOwner.TRIGGER)
                log.info("[CHAT] Session closed. Audio ownership returned to TRIGGER mode.")


def _reclaim_port(port: int = 8765) -> None:
    """Terminates any stale background process listening on the WebSocket port on Windows."""
    if sys.platform != "win32":
        return
    try:
        cmd = f"netstat -ano | findstr :{port}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        current_pid = os.getpid()
        for line in res.stdout.strip().splitlines():
            if "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = int(parts[-1])
                    if pid > 0 and pid != current_pid:
                        log.info("[BRIDGE] Reclaiming port %d from stale process PID %d...", port, pid)
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
    except Exception as e:
        log.debug("Port reclaim error: %s", e)


def main() -> int:
    global UI_PROCESS
    blocksize = block_samples()

    # Reclaim port 8765 from any orphan background processes
    _reclaim_port(getattr(bridge, "port", 8765))

    # Start JarvisBridge WebSocket Server
    bridge.start()

    # Launch desktop UI overlay process once in background if enabled
    LAUNCH_DESKTOP_UI = os.environ.get("JARVIS_LAUNCH_DESKTOP_UI", "True").strip().lower() in ("true", "1", "yes")
    if LAUNCH_DESKTOP_UI and sys.platform == "win32":
        try:
            ui_script = Path(__file__).resolve().parent / "ui_window.py"
            if ui_script.is_file():
                _cleanup_ui_process()
                popen_kw: dict = {
                    "args": [sys.executable, str(ui_script)],
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
                popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
                UI_PROCESS = subprocess.Popen(**popen_kw)
                log.info("Launched Jarvis desktop UI overlay process (hidden by default, PID: %d).", UI_PROCESS.pid)
                if _UI_JOB_OBJECT is not None and sys.platform == "win32":
                    try:
                        import ctypes
                        # Assign child process handle to job object
                        ctypes.windll.kernel32.AssignProcessToJobObject(_UI_JOB_OBJECT, int(UI_PROCESS._handle))
                    except Exception as je:
                        log.debug("Job object assign note: %s", je)
        except Exception as e:
            log.warning("Could not launch desktop UI overlay: %s", e)

    # Initialize Central AudioManager (Single Microphone Pipeline)
    audio_mgr = AudioManager.get_instance(sample_rate=SAMPLE_RATE, block_ms=BLOCK_MS)
    coordinator = JarvisCoordinator(audio_mgr, blocksize)

    # Register listeners for TRIGGER and CHAT modes
    audio_mgr.register_listener(AudioOwner.TRIGGER, coordinator.process_trigger_frame)
    audio_mgr.register_listener(AudioOwner.CHAT, coordinator.process_chat_frame)

    # Register Barge-In Interruption Handler (Stops playback when speech begins)
    from audio.playback import SoundDevicePlayback
    audio_mgr.register_barge_in_handler(SoundDevicePlayback.get_instance().stop)

    # Default to TRIGGER mode ownership on startup
    audio_mgr.acquire(AudioOwner.TRIGGER)

    log.info("===============================================================")
    log.info(" JARVIS RUNTIME COORDINATOR — HERMES AGENT & SINGLE AUDIO OWNER")
    log.info("===============================================================")
    log.info(" Microphone Invariant: Central AudioManager (Single Stream)")
    log.info(" Mode 1: TRIGGER MODE (Claps & Deterministic Shortcuts)")
    log.info(" Mode 2: CHAT MODE (VAD + STT + Hermes Agent + Computer Use)")
    log.info(" Activation: 'Hey Jarvis, I need your help' -> Chat Mode & Hermes")
    log.info(" Deactivation: 'Jarvis, go to sleep' -> Return to Trigger Mode")
    log.info(" Audio capture: Rate=%d Hz, Block=%d ms", SAMPLE_RATE, BLOCK_MS)
    log.info("===============================================================")

    while True:
        try:
            input_idx = _choose_input_device(blocksize)
            coordinator.stream_start_time = time.monotonic()
            last_mem_trim = time.monotonic()
            with sd.InputStream(
                device=input_idx,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=blocksize,
            ) as stream:
                while True:
                    try:
                        data, overflowed = stream.read(blocksize)
                        if overflowed:
                            log.debug("Input overflow; try a larger BLOCK_MS")

                        now = time.monotonic()
                        audio_mgr.process_incoming_frame(data, now)

                        # Periodic memory trim every 15 seconds when idle
                        if now - last_mem_trim >= 15.0:
                            last_mem_trim = now
                            if not bridge.is_conversation_active():
                                try:
                                    import gc
                                    gc.collect()
                                    if sys.platform == "win32":
                                        import ctypes
                                        ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
                                except Exception:
                                    pass
                    except sd.PortAudioError as pe:
                        log.warning("Recoverable PortAudio stream glitch: %s. Reconnecting stream in 0.5s...", pe)
                        time.sleep(0.5)
                        break
                    except Exception as fe:
                        log.warning("Recoverable audio frame processing warning: %s", fe)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            audio_mgr.release()
            return 0
        except Exception as e:
            log.warning("Audio stream exception: %s. Reconnecting in 1.0s...", e)
            time.sleep(1.0)

    return 0


if __name__ == "__main__":
    sys.exit(main())



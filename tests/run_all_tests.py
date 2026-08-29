from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

TEST_FILES = [
    "test_audio_preprocessor.py",
    "test_vad.py",
    "test_audio_manager.py",
    "test_smart_stt.py",
    "test_bilingual_stt_resolver.py",
    "test_code_switching.py",
    "test_normalizer.py",
    "test_command_understanding.py",
    "test_language_detector.py",
    "test_agent.py",
    "test_ui_perception.py",
    "test_tts_pipeline.py",
    "test_playback_barge_in.py",
    "test_memory.py",
    "benchmark_bilingual_stt.py",
]

def main() -> int:
    tests_dir = Path(__file__).resolve().parent
    root_dir = tests_dir.parent
    os.chdir(root_dir)

    print("=" * 70)
    print(" JARVIS VOICE ENGINE & AGENT ARCHITECTURE - INTEGRATION TEST SUITE")
    print("=" * 70)

    total = len(TEST_FILES)
    passed = 0
    failed = []

    start_time = time.time()

    for idx, test_file in enumerate(TEST_FILES, 1):
        test_path = tests_dir / test_file
        print(f"[{idx}/{total}] Running {test_file}...", end=" ", flush=True)

        test_env = dict(os.environ, PYTHONIOENCODING="utf-8")
        res = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=test_env,
        )

        if res.returncode == 0:
            print("[PASSED]")
            passed += 1
        else:
            print("[FAILED]")
            print(f"--- STDOUT ---\n{res.stdout}")
            print(f"--- STDERR ---\n{res.stderr}")
            failed.append(test_file)

    elapsed = time.time() - start_time
    print("=" * 70)
    print(f"TEST SUMMARY: {passed}/{total} PASSED in {elapsed:.2f}s")
    if failed:
        print(f"Failed tests: {failed}")
        return 1
    else:
        print("ALL TESTS PASSED SUCCESSFULLY!")
        return 0

if __name__ == "__main__":
    sys.exit(main())

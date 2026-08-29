"""
Voice Memory & Phonetic Guessing Engine:
1. Normalizes and autocorrects misheard/accented speech using phonetic patterns & fuzzy matching.
2. Supports Vietnamese and Vietnamese-English accent pronunciation variations.
3. Persists learned user phrase mappings to 'user_voice_memory.json'.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("voice_memory")

MEMORY_FILE = Path(__file__).resolve().parent.parent / "user_voice_memory.json"


class VoiceMemory:
    """
    Intelligent Phonetic Guessing and Self-Learning Voice Memory.
    """

    _instance: VoiceMemory | None = None

    @classmethod
    def get_instance(cls) -> VoiceMemory:
        if cls._instance is None:
            cls._instance = VoiceMemory()
        return cls._instance

    # Default Built-in Phonetic & Accent Dictionaries
    BUILTIN_PATTERNS: dict[str, str] = {
        # Browser / Chrome Opening
        "orban browsers": "open chrome",
        "orban browser": "open chrome",
        "all been browser": "open chrome",
        "open graham": "open chrome",
        "opened graham": "open chrome",
        "poland graham": "open chrome",
        "over browser": "open chrome",
        "oh but browser": "open chrome",
        "all but browser": "open chrome",
        "albany browse": "open chrome",
        "oh open rosa": "open chrome",
        "mo browser": "open chrome",
        "mo chrome": "open chrome",
        "bat browser": "open chrome",
        "bat chrome": "open chrome",
        "open brother": "open chrome",

        # YouTube Opening & Accents
        "enter youtube": "open youtube",
        "enter you too": "open youtube",
        "in the u the": "open youtube",
        "you too": "open youtube",
        "u tube": "open youtube",
        "du tup": "open youtube",
        "du tu be": "open youtube",
        "mo youtube": "open youtube",
        "bat youtube": "open youtube",
        "orban youtube": "open youtube",
        "oh but you": "open youtube",
        "open you up": "open youtube",
        "enter you the": "open youtube",
        "entered youtube": "open youtube",
        "oh would you tip": "open youtube",
        "i'll bet you tip": "open youtube",
        "open your dip": "open youtube",
        "you tip": "open youtube",
        "u tip": "open youtube",
        "malkin you": "open youtube",
        "malcolm you": "open youtube",

        # Search / Find cues recognized with accents
        "suggests": "search",
        "suggest": "search",
        "shout": "search",
        "shut": "search",
        "search for": "search",
        "five for me": "find for me",
        "fine for me": "find for me",
        "das cbt": "chatgpt",
        "yeah cbt": "chatgpt",
        "see the right": "chatgpt",
        "sigh jass cpt": "search chatgpt",
        "snap yeah see the right": "search chatgpt",

        # YouTube Video Selection / Click & Play
        "play video 1": "click first video",
        "play video one": "click first video",
        "play video 2": "click second video",
        "play video two": "click second video",
        "play video 3": "click third video",
        "play first video": "click first video",
        "play the first video": "click first video",
        "played a first video": "click first video",
        "play second video": "click second video",
        "play the second video": "click second video",
        "bat video 1": "click first video",
        "bat video dau tien": "click first video",
        "mo video 1": "click first video",
        "phat video 1": "click first video",
        "phat video dau tien": "click first video",
        "chon video 1": "click first video",
        "chon video 2": "click second video",
        "chon video 3": "click third video",
        "les second videos": "click second video",
        "place second videos": "click second video",
        "rick on know second video jealous": "click second video",
        "rick on know second video": "click second video",
        "play second video service": "click second video",
        "the second video": "click second video",
        "second video": "click second video",
        "click on the second video": "click second video",
        "chon video thu hai": "click second video",
        "chon video thu 2": "click second video",
        "video thu hai": "click second video",
        "video thu 2": "click second video",

        "first video": "click first video",
        "the first video": "click first video",
        "click first video": "click first video",
        "chon video thu nhat": "click first video",
        "chon video thu 1": "click first video",
        "chon video dau tien": "click first video",
        "video dau tien": "click first video",
        "video thu 1": "click first video",
        "video 1": "click first video",
        "video 2": "click second video",
        "video 3": "click third video",

        "third video": "click third video",
        "the third video": "click third video",
        "play third video": "click third video",
        "chon video thu ba": "click third video",
        "chon video thu 3": "click third video",

        # Window Positioning & Snapping
        "top right": "top_right",
        "top left": "top_left",
        "bottom right": "bottom_right",
        "bottom left": "bottom_left",
        "keo sang trai": "snap_left",
        "keo sang phai": "snap_right",
        "nua trai": "snap_left",
        "nua phai": "snap_right",
        "chia doi sang trai": "snap_left",
        "chia doi sang phai": "snap_right",
        "mo lon cua so": "maximize_window",
        "mo cua so lon ra": "maximize_window",
        "phong to cua so": "maximize_window",
        "thu nho cua so": "minimize_window",
        "an cua so": "minimize_window",
        "dua vao giua": "center_window",
        "giua man hinh": "center_window",

        # Tab Navigation & Management
        "tab tiep theo": "next_tab",
        "chuyen tab": "next_tab",
        "next tab": "next_tab",
        "tab truoc": "previous_tab",
        "previous tab": "previous_tab",
        "quay lai tab truoc": "previous_tab",
        "mo tab moi": "new_tab",
        "tao tab moi": "new_tab",
        "new tab": "new_tab",
        "dong tab": "close_tab",
        "tat tab": "close_tab",
        "close tab": "close_tab",
        "khoi phuc tab": "reopen_tab",
        "mo lai tab": "reopen_tab",
        "reopen tab": "reopen_tab",
        "chon tab 1": "select_tab_1",
        "tab 1": "select_tab_1",
        "tab dau tien": "select_tab_1",
        "first tab": "select_tab_1",
        "chon tab 2": "select_tab_2",
        "tab 2": "select_tab_2",
        "tab thu 2": "select_tab_2",
        "second tab": "select_tab_2",
        "chon tab 3": "select_tab_3",
        "tab 3": "select_tab_3",
        "tab thu 3": "select_tab_3",
        "third tab": "select_tab_3",
        "chon tab 4": "select_tab_4",
        "tab 4": "select_tab_4",
        "chon tab cuoi": "select_tab_last",
        "tab cuoi cung": "select_tab_last",
        "last tab": "select_tab_last",

        # Window Switching
        "switch window": "switch_window",
        "switch windows": "switch_window",
        "sweet window": "switch_window",
        "change window": "switch_window",
        "next window": "switch_window",
        "alt tab": "switch_window",
        "doi cua so": "switch_window",
        "chuyen cua so": "switch_window",
        "chuyen tab": "switch_window",
        "cua so tiep theo": "switch_window",
        "switch to chrome": "switch to chrome",
        "switch to vscode": "switch to vscode",
        "switch to code": "switch to vscode",
        "switch to antigravity": "switch to antigravity",
        "switch to spotify": "switch to spotify",

        # Window Closing & Phonetic Variations
        "klaus that youtube window": "close youtube",
        "blows youtube window": "close youtube",
        "klaus cool read window": "close chrome",
        "klaus cool run with bill": "close chrome",
        "klaus cool read we know": "close chrome",
        "klaus that we know": "close_window",
        "blouse the with know": "close_window",
        "klaus": "close",
        "blows": "close",
        "claws": "close",
        "cool read": "chrome",
        "cool run": "chrome",
        "we know": "window",
        "with know": "window",
        "with bill": "window",
        "close window": "close_window",
        "close windows": "close_window",
        "closed window": "close_window",
        "closed windows": "close_window",
        "close the window": "close_window",
        "cloth window": "close_window",
        "cross window": "close_window",
        "claws window": "close_window",
        "close wind": "close_window",
        "close win": "close_window",
        "close current window": "close_window",
        "close tab": "close_window",
        "dong cua so": "close_window",
        "tat cua so": "close_window",
        "dong tab": "close_window",
        "tat tab": "close_window",
        "dong lai": "close_window",
        "quit window": "close_window",
        "close youtube": "close_window",
        "close chrome": "close_window",

        # Window Minimize / Maximize
        "minimize window": "minimize_window",
        "minimize": "minimize_window",
        "thu nho cua so": "minimize_window",
        "an cua so": "minimize_window",
        "maximize window": "maximize_window",
        "maximize": "maximize_window",
        "phong to cua so": "maximize_window",
        "toan man hinh": "maximize_window",
        "fullscreen": "maximize_window",

        # VS Code / Code
        "open vs code": "open vs code",
        "open code": "open vs code",
        "open vscode": "open vs code",
        "mo vs code": "open vs code",
        "mo code": "open vs code",

        # Sleep / Dismiss
        "will slip": "go to sleep",
        "slip": "go to sleep",
        "cabbies": "go to sleep",
        "japanese go to sleep": "go to sleep",
        "chavis go to sleep": "go to sleep",
        "di ngu di": "go to sleep",
        "tat di": "go to sleep",
    }

    def __init__(self):
        self.memory_path = MEMORY_FILE
        self.user_learned: dict[str, str] = {}
        self._load_memory()

    def _load_memory(self) -> None:
        """Load user learned phrases from JSON file."""
        if self.memory_path.is_file():
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    self.user_learned = json.load(f)
                log.info("[VOICE_MEMORY] Loaded %d learned phrase mappings from %s", len(self.user_learned), self.memory_path.name)
            except Exception as e:
                log.warning("[VOICE_MEMORY] Could not load memory file: %s", e)
                self.user_learned = {}

    def save_memory(self) -> None:
        """Persist learned mappings to disk."""
        try:
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(self.user_learned, f, indent=2, ensure_ascii=False)
            log.info("[VOICE_MEMORY] Saved %d learned phrase mappings to disk.", len(self.user_learned))
        except Exception as e:
            log.warning("[VOICE_MEMORY] Could not save memory file: %s", e)

    APP_KEYWORDS = {"chrome", "browser", "youtube", "vscode", "code", "spotify", "antigravity", "notepad", "calculator"}
    ACTION_KEYWORDS = {"open", "close", "mo", "bat", "dong", "tat", "switch", "chuyen", "doi", "next", "prev", "play", "pause"}

    def learn(self, user_phrase: str, canonical_command: str) -> None:
        """Associate a user's spoken phrase with an intended canonical command."""
        p = user_phrase.strip().lower()
        c = canonical_command.strip().lower()

        if not p or not c or p == c:
            return

        # Prevent contradictory associations (open vs close)
        if ("close" in p or "dong" in p or "tat" in p) and ("open" in c or "mo" in c or "bat" in c):
            return
        if ("open" in p or "mo" in p or "bat" in p) and ("close" in c or "dong" in c or "tat" in c):
            return

        # Prevent swapping different applications (e.g. chrome -> code)
        p_apps = {w for w in p.split() if w in self.APP_KEYWORDS}
        c_apps = {w for w in c.split() if w in self.APP_KEYWORDS}
        if p_apps and c_apps and p_apps != c_apps:
            log.warning("[VOICE_MEMORY] Refused to learn cross-app mapping: '%s' -> '%s'", p, c)
            return

        self.user_learned[p] = c
        self.save_memory()
        log.info("[VOICE_MEMORY] Learned new mapping: '%s' -> '%s'", p, c)

    def normalize(self, text: str) -> tuple[str, bool]:
        """
        Normalize and guess the intended command from recognized speech.
        Returns:
            (predicted_text: str, is_corrected: bool)
        """
        raw = text.strip().lower()
        if not raw:
            return text, False

        # 1. Exact match in learned memory
        if raw in self.user_learned:
            corrected = self.user_learned[raw]
            log.info("[VOICE_MEMORY] Exact match in learned memory: '%s' -> '%s'", raw, corrected)
            return corrected, True

        # 2. Exact match in built-in dictionary
        if raw in self.BUILTIN_PATTERNS:
            corrected = self.BUILTIN_PATTERNS[raw]
            log.info("[VOICE_MEMORY] Exact match in phonetic dictionary: '%s' -> '%s'", raw, corrected)
            return corrected, True

        # 3. Whole-word / Phrase regex replacements (sorted longest-key-first)
        all_patterns = {**self.BUILTIN_PATTERNS, **self.user_learned}
        sorted_keys = sorted(all_patterns.keys(), key=len, reverse=True)
        replaced = raw
        has_changed = False

        for misheard in sorted_keys:
            canonical = all_patterns[misheard]
            pattern = r'\b' + re.escape(misheard) + r'\b'
            if re.search(pattern, replaced):
                replaced = re.sub(pattern, canonical, replaced).strip()
                has_changed = True

        if has_changed:
            log.info("[VOICE_MEMORY] Phonetic phrase substitution: '%s' -> '%s'", raw, replaced)
            return replaced, True

        # 4. If phrase is already a known canonical command, do not fuzzy-mutate it
        known_canonical = set(all_patterns.values())
        if raw in known_canonical:
            return raw, False

        # 5. Fuzzy Matching across known commands (strict threshold 0.88)
        matches = difflib.get_close_matches(raw, list(all_patterns.keys()), n=1, cutoff=0.88)
        if matches:
            best_match = matches[0]
            corrected = all_patterns[best_match]

            # Verify no open/close contradiction
            if (("close" in raw or "dong" in raw) and ("open" in corrected or "mo" in corrected)) or \
               (("open" in raw or "mo" in raw) and ("close" in corrected or "dong" in corrected)):
                return text, False

            # Verify no app swapping (e.g. chrome vs code)
            raw_apps = {w for w in raw.split() if w in self.APP_KEYWORDS}
            corr_apps = {w for w in corrected.split() if w in self.APP_KEYWORDS}
            if raw_apps and corr_apps and raw_apps != corr_apps:
                return text, False

            log.info("[VOICE_MEMORY] Fuzzy guess match (sim=%.2f): '%s' -> '%s' (via '%s')",
                     difflib.SequenceMatcher(None, raw, best_match).ratio(), raw, corrected, best_match)
            self.learn(raw, corrected)
            return corrected, True

        return text, False

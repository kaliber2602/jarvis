"""
Data-driven Bilingual Verb Lexicon for Jarvis Command Understanding Engine.
Maps surface natural language verbs/phrases in English and Vietnamese to Canonical Verbs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger("verb_lexicon")


class CanonicalVerb:
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    STOP = "STOP"
    SEARCH = "SEARCH"
    CREATE = "CREATE"
    DELETE = "DELETE"
    SEND = "SEND"
    TYPE = "TYPE"
    SWITCH = "SWITCH"
    SCROLL = "SCROLL"
    SNAP = "SNAP"
    TAB = "TAB"
    SLEEP = "SLEEP"
    SYSTEM_QUERY = "SYSTEM_QUERY"


@dataclass
class VerbDefinition:
    canonical: str
    intent: str
    surface_forms_en: list[str] = field(default_factory=list)
    surface_forms_vi: list[str] = field(default_factory=list)


class VerbLexicon:
    """
    Extensible Data-Driven Verb Lexicon.
    Allows adding new verbs or synonyms dynamically without modifying parser code.
    """

    _instance: VerbLexicon | None = None

    @classmethod
    def get_instance(cls) -> VerbLexicon:
        if cls._instance is None:
            cls._instance = VerbLexicon()
        return cls._instance

    def __init__(self):
        self._definitions: dict[str, VerbDefinition] = {}
        self._surface_to_canonical: dict[str, str] = {}
        self._canonical_to_intent: dict[str, str] = {}
        self._compiled_patterns: list[tuple[re.Pattern, str, str, float]] = []
        self._init_default_lexicon()

    def _init_default_lexicon(self) -> None:
        """Populate standard English and Vietnamese verb lexicons."""
        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.OPEN,
            intent="OPEN_APPLICATION",
            surface_forms_en=[
                "open", "launch", "start", "run", "fire up", "bring up", "start up",
                "open up", "execute", "access"
            ],
            surface_forms_vi=[
                "mở", "khởi chạy", "chạy", "bật", "mở lên", "bật lên", "bật app", "mở app",
                "mở ứng dụng", "khởi động", "truy cập"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.CLOSE,
            intent="CLOSE_APPLICATION",
            surface_forms_en=[
                "close", "exit", "quit", "shut down", "kill", "close down", "terminate",
                "dismiss", "close window", "close tab"
            ],
            surface_forms_vi=[
                "đóng", "thoát", "tắt", "tắt đi", "đóng lại", "tắt cửa sổ", "đóng cửa sổ",
                "tắt ứng dụng", "đóng ứng dụng", "hủy"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.PLAY,
            intent="MEDIA_CONTROL",
            surface_forms_en=[
                "play", "start playing", "resume", "play music", "play song", "play track",
                "play playlist"
            ],
            surface_forms_vi=[
                "phát", "mở nhạc", "phát nhạc", "bật nhạc", "bật bài", "nghe nhạc", "chơi nhạc",
                "tiếp tục phát"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.PAUSE,
            intent="MEDIA_CONTROL",
            surface_forms_en=["pause", "pause music", "pause playback", "hold"],
            surface_forms_vi=["tạm dừng", "dừng lại", "tạm ngưng", "dừng nhạc", "ngưng nhạc"]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.STOP,
            intent="MEDIA_CONTROL",
            surface_forms_en=["stop", "halt", "stop music", "stop playing"],
            surface_forms_vi=["dừng", "ngừng", "dừng hẳn", "tắt nhạc"]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SEARCH,
            intent="SEARCH_WEB",
            surface_forms_en=[
                "search", "find", "look for", "look up", "google", "search for", "query",
                "seek", "browse for"
            ],
            surface_forms_vi=[
                "tìm", "tìm kiếm", "tra", "tra cứu", "tìm cho tôi", "kiếm", "tra thông tin",
                "tìm thông tin", "search"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.CREATE,
            intent="FILE_MANAGEMENT",
            surface_forms_en=["create", "make", "generate", "new", "compose", "build"],
            surface_forms_vi=["tạo", "tạo mới", "sinh", "lập", "tạo ra"]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.DELETE,
            intent="FILE_MANAGEMENT",
            surface_forms_en=["delete", "remove", "erase", "trash", "discard"],
            surface_forms_vi=["xóa", "loại bỏ", "xóa bỏ", "hủy bỏ"]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SEND,
            intent="COMMUNICATION",
            surface_forms_en=["send", "forward", "transmit", "dispatch"],
            surface_forms_vi=["gửi", "chuyển tiếp", "bắn qua", "gửi đi"]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.TYPE,
            intent="INPUT_CONTROL",
            surface_forms_en=["type", "enter", "write", "input", "fill in"],
            surface_forms_vi=["gõ", "nhập", "viết", "điền"]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SWITCH,
            intent="FOCUS_APPLICATION",
            surface_forms_en=[
                "switch", "change", "switch to", "focus", "bring to front", "switch window",
                "switch to window", "alt tab"
            ],
            surface_forms_vi=[
                "chuyển", "đổi", "thay đổi", "chuyển sang", "chuyển qua", "qua", "sang",
                "đổi sang", "chuyển cửa sổ", "đổi cửa sổ", "focus vào"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SCROLL,
            intent="WINDOW_MANAGEMENT",
            surface_forms_en=[
                "scroll down", "scroll up", "roll down", "roll up", "scroll", "roll",
                "page down", "page up"
            ],
            surface_forms_vi=[
                "cuộn xuống", "cuộn lên", "lướt xuống", "lướt lên", "kéo xuống", "kéo lên",
                "cuộn trang", "lướt trang", "cuộn", "lướt"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SNAP,
            intent="WINDOW_MANAGEMENT",
            surface_forms_en=[
                "snap left", "snap right", "maximize", "minimize", "fullscreen",
                "half left", "half right", "split left", "split right", "center window", "snap"
            ],
            surface_forms_vi=[
                "kéo sang trái", "kéo sang phải", "nửa trái", "nửa phải", "chia đôi màn hình",
                "phóng to", "thu nhỏ", "toàn màn hình", "căn giữa", "kéo sang"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.TAB,
            intent="TAB_MANAGEMENT",
            surface_forms_en=[
                "next tab", "previous tab", "new tab", "close tab", "reopen tab",
                "select tab", "switch tab", "switch to tab", "tab"
            ],
            surface_forms_vi=[
                "tab tiếp theo", "tab trước", "mở tab mới", "đóng tab", "tắt tab",
                "khôi phục tab", "chọn tab", "chuyển tab", "đổi tab", "chuyển sang tab",
                "chuyển qua tab", "sang tab", "qua tab"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SLEEP,
            intent="SLEEP_DISMISS",
            surface_forms_en=[
                "go to sleep", "jarvis go to sleep", "sleep now", "dismiss", "goodbye",
                "shut down jarvis", "close jarvis"
            ],
            surface_forms_vi=[
                "đi ngủ đi", "đi ngủ", "ngủ đi", "nghỉ ngơi đi", "tắt đi", "tạm biệt jarvis",
                "đóng jarvis"
            ]
        ))

        self.register_definition(VerbDefinition(
            canonical=CanonicalVerb.SYSTEM_QUERY,
            intent="SYSTEM_QUERY",
            surface_forms_en=[
                "system status", "battery status", "cpu usage", "ram usage", "system health",
                "check status", "system info"
            ],
            surface_forms_vi=[
                "kiểm tra hệ thống", "tình trạng máy", "dung lượng pin", "dung lượng ram",
                "thông tin hệ thống", "trạng thái máy"
            ]
        ))

    def register_definition(self, defn: VerbDefinition) -> None:
        """Register or override a verb definition in the lexicon."""
        self._definitions[defn.canonical] = defn
        self._canonical_to_intent[defn.canonical] = defn.intent

        # Combine all surface forms
        all_forms = defn.surface_forms_en + defn.surface_forms_vi
        for form in all_forms:
            cleaned = form.strip().lower()
            if cleaned:
                self._surface_to_canonical[cleaned] = defn.canonical

        self._recompile_patterns()

    def _recompile_patterns(self) -> None:
        """Compile regex patterns ordered by longest phrase first to ensure maximum greedy matching."""
        # Sort surface phrases by word count / length descending
        sorted_forms = sorted(self._surface_to_canonical.keys(), key=lambda s: (-len(s.split()), -len(s)))
        self._compiled_patterns.clear()

        for form in sorted_forms:
            canonical = self._surface_to_canonical[form]
            # Match whole phrase with word boundaries or start of clause
            pattern = re.compile(rf"(?:\b|^){re.escape(form)}(?:\b|$)", re.IGNORECASE)
            self._compiled_patterns.append((pattern, form, canonical, 0.98 if len(form.split()) > 1 else 0.95))

    def find_verb(self, text: str) -> Optional[Tuple[str, str, str, float]]:
        """
        Scan text and find the first matching canonical verb.
        Returns:
            (canonical_verb, matched_surface_form, intent, confidence) or None.
        """
        cleaned = text.strip().lower()
        if not cleaned:
            return None

        for pattern, surface, canonical, conf in self._compiled_patterns:
            if pattern.search(cleaned):
                intent = self._canonical_to_intent.get(canonical, "UNKNOWN")
                return canonical, surface, intent, conf

        return None

    def get_intent_for_canonical(self, canonical: str) -> str:
        return self._canonical_to_intent.get(canonical, "UNKNOWN")

    def get_all_canonical_verbs(self) -> list[str]:
        return list(self._definitions.keys())

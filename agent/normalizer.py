"""
Voice Normalization & Semantic Interpretation Layer for Jarvis.
Provides:
1. Transcript Normalization (Deduplication, Diacritic transliteration, Noise filtering).
2. Multi-Signal Entity Resolution (AppRegistry, Technical Vocabulary, Phonetics).
3. Context-Aware Semantic Intent Detection (Open, Close, Focus, Search, Compound tasks).
4. Rich Structured InterpretationContext for deterministic fast-path and Hermes reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any

from .app_registry import AppInfo, AppRegistry
from .phonetics import (
    calculate_entity_similarity,
    remove_vietnamese_diacritics,
    transliterate_vietnamese_phonetics,
)

log = logging.getLogger("normalizer")


@dataclass
class EntityCandidate:
    name: str
    canonical_id: str
    entity_type: str  # "application" | "tech_term" | "url" | "target"
    confidence: float
    app_info: AppInfo | None = None
    matched_alias: str = ""
    match_method: str = "exact"
    span: tuple[int, int] = (0, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "canonical_id": self.canonical_id,
            "entity_type": self.entity_type,
            "confidence": round(self.confidence, 4),
            "matched_alias": self.matched_alias,
            "match_method": self.match_method,
            "span": list(self.span),
            "executable": self.app_info.executable if self.app_info else None,
        }


@dataclass
class InterpretationContext:
    raw_transcript: str
    normalized_transcript: str
    intent: str
    target_entity: EntityCandidate | None = None
    entities: list[EntityCandidate] = field(default_factory=list)
    confidence: float = 0.0
    is_compound: bool = False
    clarification_needed: bool = False
    clarification_prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_transcript": self.raw_transcript,
            "normalized_transcript": self.normalized_transcript,
            "intent": self.intent,
            "target_entity": self.target_entity.to_dict() if self.target_entity else None,
            "entities": [e.to_dict() for e in self.entities],
            "confidence": round(self.confidence, 4),
            "is_compound": self.is_compound,
            "clarification_needed": self.clarification_needed,
            "clarification_prompt": self.clarification_prompt,
            "metadata": self.metadata,
        }


class TranscriptNormalizer:
    """Cleans, deduplicates, and transliterates raw transcript text."""

    FILLER_NOISE_WORDS = {
        "ah", "oh", "um", "uh", "eh", "er", "hm", "hmm", "mm", "the", "a",
        "so", "yeah", "no", "oh up", "what a man", "right yeah no", "you know i know",
        "yeah this", "oh yeah", "now", "up", "ạ", "ờ", "ừ", "hả", "nè"
    }

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Remove redundant whitespace and abnormal characters."""
        if not text:
            return ""
        t = re.sub(r"\s+", " ", text).strip()
        return t

    @classmethod
    def strip_dangling_trailing_verbs(cls, text: str) -> str:
        """Strip incomplete trailing verbs or conjunctions caused by speech cutoffs."""
        if not text:
            return ""
        t = text.strip()
        dangling_pattern = r"(?:[\s,;.!?]+(?:mở|open|bật|đóng|close|tắt|chạy|run|search|tìm|và|and|then|rồi|sau đó|nhưng|hoặc|or))+$"
        t_cleaned = re.sub(dangling_pattern, "", t, flags=re.IGNORECASE).strip()
        return t_cleaned if t_cleaned else t

    @classmethod
    def transliterate_phonetics(cls, text: str) -> str:
        """Transliterate phonetic Vietnamese approximations to English."""
        return transliterate_vietnamese_phonetics(text)


class EntityResolver:
    """Resolves application and technical domain entities from transcript tokens."""

    def __init__(self, registry: AppRegistry | None = None):
        self.registry = registry or AppRegistry.get_instance()

    def resolve_application(self, phrase: str) -> EntityCandidate | None:
        """
        Resolve a single application name phrase with multi-signal matching.
        """
        p = phrase.strip().lower()
        if not p or len(p) < 2:
            return None

        # Ignore generic verbs, window/tab keywords and specifiers so they are never resolved as application names
        generic_excluded_keywords = (
            "cửa sổ", "cua so", "cửa sổ này", "cua so nay", "cửa sổ hiện tại", "cua so hien tai",
            "tab này", "cửa sổ đang mở", "cửa sổ khác", "window", "windows", "tab", "tabs",
            "cửa", "cua", "sổ", "so", "mở sổ", "mo so", "đóng sổ", "dong so", "đổi sổ", "doi so",
            "mở cửa sổ", "mo cua so", "đóng cửa sổ", "dong cua so", "chuyển sổ", "chuyen so",
            "đóng cửa", "dong cua", "mở cửa", "mo cua", "tắt cửa", "tat cua", "bật cửa", "bat cua",
            "đóng", "dong", "mở", "mo", "tắt", "tat", "bật", "bat", "chạy", "chay", "tìm", "tim",
            "xem", "chuyển", "chuyen", "đổi", "doi", "thoát", "thoat", "hạ", "ha", "phóng", "phong",
            "hiện tại", "hien tai", "này", "nay", "đó", "do", "kia", "ở", "o", "trong", "trên", "tren",
            "dưới", "duoi", "cái", "cai", "con", "thứ", "thu", "số", "so", "ứng dụng", "ung dung",
            "tiến trình", "tien trinh", "phần mềm", "phan mem", "trang", "web", "current window", "this window"
        )
        if (p in generic_excluded_keywords
            or any(kw == p or p.startswith(kw + " ") or p.endswith(" " + kw) for kw in ("cửa sổ", "cua so", "window", "windows", "tab", "tabs"))
            or p.startswith("đóng") or p.startswith("dong")
            or p.startswith("mở") or p.startswith("mo")
            or p.startswith("tắt") or p.startswith("tat")
            or p.startswith("bật") or p.startswith("bat")):
            # Check exact match only if not in generic exclusions
            if p not in generic_excluded_keywords:
                exact_app = self.registry.find_by_exact_alias(p)
                if exact_app:
                    return EntityCandidate(
                        name=exact_app.display_name,
                        canonical_id=exact_app.canonical_id,
                        entity_type="application",
                        confidence=0.98,
                        app_info=exact_app,
                        matched_alias=p,
                        match_method="exact_alias",
                    )
            return None

        # 1. Exact alias lookup in AppRegistry
        exact_app = self.registry.find_by_exact_alias(p)
        if exact_app:
            return EntityCandidate(
                name=exact_app.display_name,
                canonical_id=exact_app.canonical_id,
                entity_type="application",
                confidence=0.98,
                app_info=exact_app,
                matched_alias=p,
                match_method="exact_alias",
            )

        # 2. Phonetic & Vietnamese transliteration check
        translit_p = transliterate_vietnamese_phonetics(p)
        translit_app = self.registry.find_by_exact_alias(translit_p)
        if translit_app:
            return EntityCandidate(
                name=translit_app.display_name,
                canonical_id=translit_app.canonical_id,
                entity_type="application",
                confidence=0.95,
                app_info=translit_app,
                matched_alias=translit_p,
                match_method="phonetic_translit",
            )

        # 3. Fuzzy & Phonetic search across all registered apps
        candidates: list[EntityCandidate] = []
        for app in self.registry.get_all_apps():
            score, matched_alias, method = calculate_entity_similarity(p, app.display_name, app.aliases)
            if score >= 0.70:
                candidates.append(EntityCandidate(
                    name=app.display_name,
                    canonical_id=app.canonical_id,
                    entity_type="application",
                    confidence=score,
                    app_info=app,
                    matched_alias=matched_alias,
                    match_method=method,
                ))

        if not candidates:
            return None

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        best = candidates[0]

        # Check for ambiguity (e.g. two very close candidates within 0.05)
        if len(candidates) >= 2:
            second = candidates[1]
            if (best.confidence - second.confidence) < 0.05 and best.canonical_id != second.canonical_id:
                # Disambiguation check (e.g., Visual Studio vs Visual Studio Code)
                if "code" in p and "code" in best.canonical_id:
                    return best
                elif "code" not in p and best.canonical_id == "vscode" and second.canonical_id == "visual_studio":
                    return second

        return best

    def extract_all_entities(self, text: str) -> list[EntityCandidate]:
        """Extract all recognized application and tech term entities in a transcript."""
        words = text.split()
        n = len(words)
        candidates: list[EntityCandidate] = []

        # Try all spans from length 1 to 4
        for window_size in range(1, min(5, n + 1)):
            for i in range(n - window_size + 1):
                span = (i, i + window_size)
                chunk = " ".join(words[i : i + window_size])
                cand = self.resolve_application(chunk)
                if cand:
                    min_thresh = 0.70 if (cand.app_info and cand.app_info.source == "curated") else 0.86
                    if cand.confidence >= min_thresh:
                        cand.span = span
                        candidates.append(cand)

        # Sort all found candidates by confidence descending, then by length
        candidates.sort(key=lambda c: (c.confidence, (c.span[1] - c.span[0])), reverse=True)

        selected: list[EntityCandidate] = []
        covered_indices: set[int] = set()

        for cand in candidates:
            cand_indices = set(range(cand.span[0], cand.span[1]))
            if not covered_indices.intersection(cand_indices):
                selected.append(cand)
                covered_indices.update(cand_indices)

        # Sort selected by appearance order
        selected.sort(key=lambda c: c.span[0])
        return selected


class IntentResolver:
    """Determines the user's semantic intent based on command cues and resolved entities."""

    INTENT_OPEN_VERBS = (
        "open", "launch", "start", "run", "mở", "bật", "chạy", "khởi động",
        "mở lên", "bật lên", "start up", "bring up", "orban", "oh but", "oh been",
        "all but", "albany", "urban", "oban", "orbin", "bat", "but"
    )

    INTENT_CLOSE_VERBS = (
        "close", "exit", "quit", "shut down", "kill", "đóng", "tắt", "thoát",
        "tắt đi", "đóng lại", "close down"
    )

    INTENT_FOCUS_VERBS = (
        "switch to", "focus", "bring to front", "switch window", "chuyển sang",
        "đổi sang", "chuyển qua", "chuyển", "đổi", "chuyển cửa sổ", "đổi cửa sổ",
        "chuyển window", "đổi window", "cửa sổ khác", "cửa sổ hiện tại", "chuyển tab",
        "đổi tab", "alt tab", "chuyen sang", "chuyen qua", "chuyen cua so", "doi cua so",
        "chuyen window", "doi window", "qua cửa sổ", "qua window", "sang cửa sổ", "sang window"
    )

    INTENT_SEARCH_VERBS = (
        "search", "google", "look up", "find", "tìm kiếm", "tìm cho tôi",
        "tra cứu", "tìm", "search for", "look for", "shot", "shout", "shaq", "shut", "sat", "share"
    )

    INTENT_MEDIA_VERBS = (
        "play", "play music", "play song", "phát nhạc", "bật nhạc", "mở nhạc",
        "bật bài", "pause", "tạm dừng", "dừng nhạc"
    )

    INTENT_WINDOW_VERBS = (
        "top right", "top left", "bottom right", "bottom left", "snap left",
        "snap right", "center", "minimize", "maximize", "fullscreen", "thu nhỏ",
        "phóng to", "toàn màn hình", "kéo sang", "chia đôi", "half left", "half right",
        "half screen", "half screen left", "half screen right", "split left", "split right",
        "left half", "right half", "minimise", "many my", "many mice"
    )

    INTENT_TAB_VERBS = (
        "next tab", "previous tab", "new tab", "close tab", "reopen tab",
        "new_tab", "previous_tab", "next_tab", "close_tab", "reopen_tab", "open tab",
        "tab 1", "tab 2", "tab 3", "tab 4", "tab tiếp theo", "tab trước", "mở tab mới",
        "khôi phục tab", "mở lại tab", "đóng tab", "tắt tab", "tab mới", "chọn tab"
    )

    INTENT_SYSTEM_VERBS = (
        "system status", "status", "battery", "cpu", "ram", "kiểm tra hệ thống",
        "tình trạng máy", "pin", "system health"
    )

    INTENT_SLEEP_VERBS = (
        "go to sleep", "jarvis go to sleep", "jarvis, go to sleep",
        "đi ngủ đi", "đi ngủ", "ngủ đi", "sleep now"
    )

    COMPOUND_CONJUNCTIONS = (
        " and ", " then ", " và ", " rồi ", " sau đó ", " tiếp theo ", " after that "
    )

    def resolve_intent(
        self,
        raw_text: str,
        normalized_text: str,
        entities: list[EntityCandidate],
        active_context: dict[str, Any] | None = None,
    ) -> tuple[str, EntityCandidate | None, float, bool, bool, str | None]:
        """
        Determine intent, target entity, confidence, is_compound, and clarification.
        """
        cleaned = normalized_text.strip().lower()

        # Determine compound command state
        conjunction_compound = any(c in f" {cleaned} " for c in self.COMPOUND_CONJUNCTIONS)
        app_entities = [e for e in entities if e.entity_type == "application"]
        split_pattern = r"[,;]|\s+và\s+|\s+then\s+|\s+rồi\s+|\s+sau đó\s+|\s+and\s+"
        raw_clauses = [c.strip() for c in re.split(split_pattern, cleaned) if c.strip()]
        actionable_clauses = [c for c in raw_clauses if len(c.split()) >= 2]
        is_compound = conjunction_compound or (len(app_entities) >= 2 and len(actionable_clauses) >= 2)

        # 0. Sleep / Dismiss
        if any(sv in cleaned for sv in self.INTENT_SLEEP_VERBS):
            return ("SLEEP_DISMISS", None, 0.99, is_compound, False, None)

        # 1. System Telemetry
        if any(sv in cleaned for sv in self.INTENT_SYSTEM_VERBS):
            return ("SYSTEM_QUERY", None, 0.95, is_compound, False, None)

        # 2. Window Layout & Snapping
        if any(wv in cleaned for wv in self.INTENT_WINDOW_VERBS):
            return ("WINDOW_MANAGEMENT", None, 0.95, is_compound, False, None)

        # 3. Tab Management
        if any(tv in cleaned for tv in self.INTENT_TAB_VERBS):
            return ("TAB_MANAGEMENT", None, 0.95, is_compound, False, None)

        # 4. Media Playback (Spotify / Music)
        if any(mv in cleaned for mv in self.INTENT_MEDIA_VERBS) and not any(ov in cleaned for ov in ("open", "mở")):
            if not any(vk in cleaned for vk in ("video", "youtube", "clip", "thứ 1", "thứ 2", "thứ 3", "first", "second", "third", "tap")):
                return ("MEDIA_CONTROL", None, 0.92, is_compound, False, None)

        # 5. Application Launching / Focusing / Closing
        has_open_verb = any(ov in f" {cleaned} " or cleaned.startswith(f"{ov} ") for ov in self.INTENT_OPEN_VERBS)
        has_close_verb = any(cv in f" {cleaned} " or cleaned.startswith(f"{cv} ") for cv in self.INTENT_CLOSE_VERBS)
        has_focus_verb = any(fv in cleaned for fv in self.INTENT_FOCUS_VERBS)
        has_search_verb = any(
            sv in f" {cleaned} " or cleaned.startswith(f"{sv} ")
            for sv in self.INTENT_SEARCH_VERBS
            if not (sv in ("google", "shut") and (has_close_verb or has_focus_verb or has_open_verb))
        )

        # Find primary application entity (first in sentence order, or highest confidence)
        primary_app = app_entities[0] if app_entities else None

        # 5. Application Launching (OPEN_APPLICATION) - prioritized when open verb and primary app exist
        if has_open_verb and primary_app:
            conf = min(0.98, primary_app.confidence + 0.05)
            if primary_app.confidence < 0.60:
                return ("OPEN_APPLICATION", primary_app, conf, is_compound, True, f"Did you mean {primary_app.name}?")
            return ("OPEN_APPLICATION", primary_app, conf, is_compound, False, None)

        # 6. Application Closing (CLOSE_APPLICATION)
        if has_close_verb:
            conf = 0.94 if primary_app else 0.88
            return ("CLOSE_APPLICATION", primary_app, conf, is_compound, False, None)

        # 7. Application Focusing (FOCUS_APPLICATION)
        if has_focus_verb:
            conf = 0.94 if primary_app else 0.88
            return ("FOCUS_APPLICATION", primary_app, conf, is_compound, False, None)

        # 8. Web Search (evaluated after open/close/focus app commands)
        if has_search_verb:
            return ("SEARCH_WEB", primary_app, 0.95, is_compound, False, None)

        # 7. Short implicit app command (e.g. user just said "VS Code" or "Chrome")
        if primary_app and len(cleaned.split()) <= 3 and primary_app.confidence >= 0.88:
            return ("OPEN_APPLICATION", primary_app, primary_app.confidence * 0.92, is_compound, False, None)

        # 8. Conversational / Natural Language fallback
        # (Preserves conversational sentences like "I wrote some code in VS Code yesterday")
        return ("CONVERSATION", primary_app, 0.85, is_compound, False, None)


class VoiceNormalizationPipeline:
    """
    Central Pipeline coordinating:
    Raw STT -> Transcript Normalization -> Entity Resolution -> Intent Interpretation -> InterpretationContext.
    """

    _instance: VoiceNormalizationPipeline | None = None

    @classmethod
    def get_instance(cls) -> VoiceNormalizationPipeline:
        if cls._instance is None:
            cls._instance = VoiceNormalizationPipeline()
        return cls._instance

    def __init__(self):
        self.app_registry = AppRegistry.get_instance()
        self.entity_resolver = EntityResolver(self.app_registry)
        self.intent_resolver = IntentResolver()

    def process_transcript(
        self,
        raw_transcript: str,
        active_context: dict[str, Any] | None = None,
    ) -> InterpretationContext:
        """
        Main pipeline entry point.
        Converts raw STT transcript into a rich, structured InterpretationContext.
        """
        raw = raw_transcript.strip()
        if not raw:
            return InterpretationContext(
                raw_transcript="",
                normalized_transcript="",
                intent="EMPTY",
                confidence=0.0,
            )

        # 1. Clean, strip dangling verbs, apply VoiceMemory phonetic mappings, and transliterate phonetics
        cleaned = TranscriptNormalizer.clean_text(raw)
        cleaned = TranscriptNormalizer.strip_dangling_trailing_verbs(cleaned)
        from .voice_memory import VoiceMemory
        vm_text, _ = VoiceMemory.get_instance().normalize(cleaned)
        transliterated = TranscriptNormalizer.transliterate_phonetics(vm_text)

        # 2. Extract Entities from canonical transliterated transcript
        entities = self.entity_resolver.extract_all_entities(transliterated)
        if not entities and cleaned == transliterated:
            entities = self.entity_resolver.extract_all_entities(cleaned)

        # 3. Resolve Intent & Target
        intent, target_entity, confidence, is_compound, clarification_needed, prompt = (
            self.intent_resolver.resolve_intent(
                raw_text=raw,
                normalized_text=transliterated,
                entities=entities,
                active_context=active_context,
            )
        )

        # 4. Build canonical normalized text
        # If open_application and high confidence, replace target span with canonical name
        normalized_str = transliterated
        if target_entity and target_entity.confidence >= 0.85 and intent in ("OPEN_APPLICATION", "CLOSE_APPLICATION", "FOCUS_APPLICATION"):
            # If command was e.g. "open viet code", normalize to "open Visual Studio Code"
            matched_alias = target_entity.matched_alias
            if matched_alias and matched_alias in normalized_str.lower():
                pattern = re.compile(re.escape(matched_alias), re.IGNORECASE)
                normalized_str = pattern.sub(target_entity.name, normalized_str, count=1)

        ctx = InterpretationContext(
            raw_transcript=raw,
            normalized_transcript=normalized_str,
            intent=intent,
            target_entity=target_entity,
            entities=entities,
            confidence=confidence,
            is_compound=is_compound,
            clarification_needed=clarification_needed,
            clarification_prompt=prompt,
            metadata={
                "transliterated": transliterated,
                "target_matched_alias": target_entity.matched_alias if target_entity else None,
                "target_method": target_entity.match_method if target_entity else None,
                "active_context": active_context or {},
            },
        )

        # Structured diagnostic logging
        log.info(
            "[STT -> INTERPRETATION]\n"
            "  [STT RAW]: '%s'\n"
            "  [NORMALIZED]: '%s'\n"
            "  [INTENT]: %s (confidence=%.2f, compound=%s)\n"
            "  [ENTITY]: %s (method=%s, confidence=%.2f)",
            ctx.raw_transcript,
            ctx.normalized_transcript,
            ctx.intent,
            ctx.confidence,
            ctx.is_compound,
            ctx.target_entity.name if ctx.target_entity else "None",
            ctx.target_entity.match_method if ctx.target_entity else "None",
            ctx.target_entity.confidence if ctx.target_entity else 0.0,
        )

        return ctx

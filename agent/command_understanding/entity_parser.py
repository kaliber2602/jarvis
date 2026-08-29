"""
Entity & Parameter Parser for Jarvis Command Understanding Engine.
Extracts target applications, web services, search queries, ordinal indices, and tool parameters.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Tuple

from agent.app_registry import AppRegistry
from agent.normalizer import EntityResolver
from .schema import TargetEntity

log = logging.getLogger("entity_parser")


class EntityParser:
    """Extracts target entities and parameters from command clauses."""

    WEB_SERVICES: dict[str, str] = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "chatgpt": "https://chatgpt.com",
        "gemini": "https://gemini.google.com",
        "claude": "https://claude.ai",
        "github": "https://github.com",
        "stackoverflow": "https://stackoverflow.com",
        "facebook": "https://www.facebook.com",
        "gmail": "https://mail.google.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
    }

    SNAP_POSITIONS: dict[str, str] = {
        "top left": "top_left", "top_left": "top_left", "nửa trên trái": "top_left",
        "top right": "top_right", "top_right": "top_right", "nửa trên phải": "top_right",
        "bottom left": "bottom_left", "bottom_left": "bottom_left", "nửa dưới trái": "bottom_left",
        "bottom right": "bottom_right", "bottom_right": "bottom_right", "nửa dưới phải": "bottom_right",
        "snap left": "left", "left": "left", "half left": "left", "nửa trái": "left", "kéo sang trái": "left",
        "snap right": "right", "right": "right", "half right": "right", "nửa phải": "right", "kéo sang phải": "right",
        "center": "center", "giữa": "center", "căn giữa": "center",
        "maximize": "maximize", "phóng to": "maximize", "toàn màn hình": "maximize", "fullscreen": "maximize",
        "minimize": "minimize", "thu nhỏ": "minimize",
    }

    def __init__(self, app_registry: AppRegistry | None = None):
        self.app_registry = app_registry or AppRegistry.get_instance()
        self.entity_resolver = EntityResolver(self.app_registry)

    def parse_target_and_params(
        self,
        clause: str,
        canonical_verb: str,
        intent: str
    ) -> Tuple[Optional[TargetEntity], dict[str, Any]]:
        """
        Parse target entity and action parameters for a specific clause.
        Returns:
            (target_entity, parameters_dict)
        """
        cleaned = clause.strip()
        params: dict[str, Any] = {}

        # 1. Parameter extraction based on Canonical Verb
        if canonical_verb == "SEARCH":
            target_entity, query = self._extract_search_target_and_query(cleaned)
            if query:
                params["query"] = query
            return target_entity, params

        elif canonical_verb == "TYPE":
            text_to_type = self._extract_type_text(cleaned)
            if text_to_type:
                params["text"] = text_to_type
            return None, params

        elif canonical_verb == "CREATE":
            target_entity, file_params = self._extract_create_params(cleaned)
            params.update(file_params)
            return target_entity, params

        elif canonical_verb == "SNAP":
            pos = self._extract_snap_position(cleaned)
            params["position"] = pos
            return None, params

        elif canonical_verb == "TAB":
            action, idx = self._extract_tab_params(cleaned)
            params["action"] = action
            if idx is not None:
                params["index"] = idx
            return None, params

        elif canonical_verb == "SCROLL":
            direction = "down" if any(d in cleaned.lower() for d in ("down", "xuống")) else "up"
            params["direction"] = direction
            return None, params

        # 2. Target application resolution (for OPEN, CLOSE, SWITCH, etc.)
        target_entity = self._resolve_application_or_web_target(cleaned)

        # 3. Check for specific YouTube video index parameter (e.g. "chọn video thứ 3")
        idx = self._extract_ordinal_index(cleaned)
        if idx is not None:
            params["index"] = idx

        return target_entity, params

    def _resolve_application_or_web_target(self, text: str) -> Optional[TargetEntity]:
        """Resolve application or web service from text tokens."""
        cleaned = text.strip()
        low = cleaned.lower()

        # Check Web services first (YouTube, Google, ChatGPT, etc.)
        for web_name, url in self.WEB_SERVICES.items():
            pattern = rf"(?:\b|^){re.escape(web_name)}(?:\b|$)"
            m = re.search(pattern, low)
            if m:
                return TargetEntity(
                    name=web_name.capitalize() if web_name != "youtube" else "YouTube",
                    canonical_id=web_name,
                    type="url",
                    confidence=0.98,
                    executable=url,
                    matched_alias=web_name,
                    match_method="exact",
                    span=m.span(),
                )

        # 1. Try stripping leading verb if present
        verb_prefix_pattern = r"^(?:open|launch|start|run|fire up|bring up|close|quit|exit|shut down|kill|mở|bật|chạy|khởi chạy|khởi động|đóng|tắt|thoát)\s+"
        stripped = re.sub(verb_prefix_pattern, "", cleaned, flags=re.IGNORECASE).strip()
        if stripped and stripped != cleaned:
            entities_stripped = self.entity_resolver.extract_all_entities(stripped)
            if entities_stripped:
                best = entities_stripped[0]
                return TargetEntity(
                    name=best.name,
                    canonical_id=best.canonical_id,
                    type="application",
                    confidence=best.confidence,
                    executable=best.app_info.executable if best.app_info else None,
                    matched_alias=best.matched_alias,
                    match_method=best.match_method,
                    span=best.span,
                )

        # 2. Multi-signal extraction via EntityResolver on full text
        entities = self.entity_resolver.extract_all_entities(cleaned)
        if entities:
            # Filter out candidates whose matched_alias is just a bare verb like "run" or "start" if other candidates exist
            valid_cands = [e for e in entities if e.matched_alias.lower() not in ("run", "start", "open", "mo", "bat", "chay", "dong", "tat")]
            best = valid_cands[0] if valid_cands else entities[0]
            return TargetEntity(
                name=best.name,
                canonical_id=best.canonical_id,
                type="application",
                confidence=best.confidence,
                executable=best.app_info.executable if best.app_info else None,
                matched_alias=best.matched_alias,
                match_method=best.match_method,
                span=best.span,
            )

        return None

    def _extract_search_target_and_query(self, text: str) -> Tuple[Optional[TargetEntity], str]:
        """Extract search provider/target and the search query string."""
        low = text.lower()
        target: Optional[TargetEntity] = None

        # Check if search target is YouTube, Google, etc.
        for web_name, url in self.WEB_SERVICES.items():
            if web_name in low:
                target = TargetEntity(
                    name=web_name.capitalize() if web_name != "youtube" else "YouTube",
                    canonical_id=web_name,
                    type="url",
                    confidence=0.95,
                    executable=url,
                    matched_alias=web_name,
                    match_method="exact",
                )
                break

        # Extract search query
        query_pattern = r"(?:search|tìm kiếm|tìm|tra cứu|google|look up|look for|find)\s+(?:on|in|for|trên|cho tôi|về)?\s*(?:youtube|google)?\s*(?:for|về|thông tin)?\s*(.+)"
        m = re.search(query_pattern, text, re.IGNORECASE)
        if m:
            query = m.group(1).strip()
            # Clean trailing prepositions/filler
            query = re.sub(r"^(?:for|về|on|trên)\s+", "", query, flags=re.IGNORECASE).strip()
            return target, query

        return target, ""

    def _extract_type_text(self, text: str) -> str:
        """Extract literal text to type: e.g. 'type hello world' -> 'hello world'."""
        m = re.search(r"(?:type|enter|write|gõ|nhập|viết)\s+(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("'\"")
        return ""

    def _extract_create_params(self, text: str) -> Tuple[Optional[TargetEntity], dict[str, Any]]:
        """Extract file creation parameters (e.g. 'create a new python file')."""
        low = text.lower()
        params: dict[str, Any] = {}

        if "python" in low or ".py" in low:
            params["language"] = "python"
            params["extension"] = ".py"
        elif "javascript" in low or ".js" in low:
            params["language"] = "javascript"
            params["extension"] = ".js"
        elif "html" in low or ".html" in low:
            params["language"] = "html"
            params["extension"] = ".html"
        elif "text" in low or ".txt" in low:
            params["language"] = "text"
            params["extension"] = ".txt"

        # Check filename if present
        fn_match = re.search(r"(?:file|tập tin|tên là)\s+([a-zA-Z0-9_\-\.]+)", text, re.IGNORECASE)
        if fn_match:
            params["filename"] = fn_match.group(1).strip()

        return None, params

    def _extract_snap_position(self, text: str) -> str:
        """Extract window snapping layout position."""
        low = text.lower()
        for phrase, pos in sorted(self.SNAP_POSITIONS.items(), key=lambda x: -len(x[0])):
            if phrase in low:
                return pos
        return "left"

    def _extract_tab_params(self, text: str) -> Tuple[str, Optional[int]]:
        """Extract tab navigation action and index."""
        low = text.lower()
        idx = self._extract_ordinal_index(text)

        if any(w in low for w in ("next", "tiếp", "kế")):
            return "next", None
        elif any(w in low for w in ("previous", "prev", "trước", "lùi")):
            return "previous", None
        elif any(w in low for w in ("new", "mới", "tạo")):
            return "new", None
        elif any(w in low for w in ("close", "đóng", "tắt")):
            return "close", None
        elif any(w in low for w in ("reopen", "khôi phục", "mở lại")):
            return "reopen", None
        elif idx is not None:
            return "select", idx

        return "next", None

    def _extract_ordinal_index(self, text: str) -> Optional[int]:
        """Extract ordinal or cardinal index numbers (e.g. 'thứ 3', '3', 'third', 'first')."""
        num_map = {
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
            "thứ 1": 1, "thứ nhất": 1, "thứ 2": 2, "thứ hai": 2, "thứ 3": 3, "thứ ba": 3,
            "thứ 4": 4, "thứ tư": 4, "thứ 5": 5, "thứ năm": 5,
            "tab 1": 1, "tab 2": 2, "tab 3": 3, "tab 4": 4, "tab 5": 5,
            "video 1": 1, "video 2": 2, "video 3": 3, "video 4": 4, "video 5": 5,
        }

        low = text.lower()
        for phrase, val in sorted(num_map.items(), key=lambda x: -len(x[0])):
            if phrase in low:
                return val

        # Direct digit match: e.g. "thứ 3" or "số 2"
        m = re.search(r"(?:thứ|số|video|tab|number)\s*(\d+)", low)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        return None

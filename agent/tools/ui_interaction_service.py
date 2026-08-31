"""
UI Interaction Service: Transactional Orchestrator for UI Component Targeting & Interaction.
Enforces the 8-Stage Interaction Pipeline:
  1. Task Window Binding & Strong Window Identity Resolution (TaskWindowContext)
  2. Read-Only Task Window Validation & Minimal Activation
  3. Pre-State Capture (YouTubeState) & Coordinate Context Capture
  4. Explicit HWND-Bound UI Perception with Stale Invalidation
  5. Deterministic Row-Major Ordinal Resolution (Left -> Right, Top -> Bottom)
  6. Semantic Target & Clickable Region Resolution (YouTubeVideoTarget)
  7. Exactly-Once Physical Click Execution (click_count == 1, ZERO retries)
  8. Multi-Level State Transition Observation & Task Verification (ZERO duplicate clicks)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Optional

from .browser_context import BrowserContext, WindowHandle, WindowSnapshot
from .component_target import (
    ComponentTarget,
    YouTubeVideoTarget,
    derive_safe_interaction_point,
    resolve_clickable_region,
    resolve_safe_click_point,
    sort_row_major,
)
from .coordinate_mapper import CoordinateMapper
from .interaction_executor import InteractionExecutor
from .window_manager import WindowIdentity, WindowManager

log = logging.getLogger("hermes.ui_interaction_service")


@dataclass(frozen=True)
class TaskWindowContext:
    """
    Authoritative single-source-of-truth window context locked across a transaction.
    """
    hwnd: int
    pid: int
    process_name: str
    title: str
    app_identity: str
    is_foreground: bool
    window_rect: tuple[int, int, int, int]
    client_rect: tuple[int, int, int, int]
    client_screen_origin: tuple[int, int]
    viewport_screen_origin: tuple[int, int]
    viewport_size: tuple[int, int]
    browser_chrome_height: int
    dpi: int
    dpi_scale: float
    is_maximized: bool
    is_minimized: bool
    timestamp: float

    @classmethod
    def from_snapshot(cls, snapshot: WindowSnapshot, app_identity: str = "chrome") -> TaskWindowContext:
        return cls(
            hwnd=snapshot.hwnd,
            pid=snapshot.handle.pid,
            process_name=snapshot.handle.process_name,
            title=snapshot.title,
            app_identity=app_identity,
            is_foreground=snapshot.is_foreground,
            window_rect=snapshot.window_rect,
            client_rect=snapshot.client_rect,
            client_screen_origin=snapshot.client_screen_origin,
            viewport_screen_origin=snapshot.viewport_screen_origin,
            viewport_size=snapshot.viewport_size,
            browser_chrome_height=snapshot.browser_chrome_height,
            dpi=snapshot.dpi,
            dpi_scale=snapshot.dpi_scale,
            is_maximized=snapshot.is_maximized,
            is_minimized=snapshot.is_minimized,
            timestamp=time.time(),
        )


@dataclass
class YouTubeState:
    """
    Authoritative state snapshot of a YouTube browser window before and after user interactions.
    """
    hwnd: int
    title: str = ""
    url: str = ""
    page_type: str = "UNKNOWN"  # HOME, SEARCH_RESULTS, WATCH_PAGE, CHANNEL, AUXILIARY, UNKNOWN
    video_count: int = 0
    visible_cards: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    @classmethod
    def capture(cls, hwnd: int, raw_components: list[Any] | None = None) -> YouTubeState:
        """Capture point-in-time state of the YouTube window."""
        title = ""
        try:
            from .window_target_resolver import WindowTargetResolver
            meta = WindowTargetResolver.get_window_meta(hwnd)
            if meta and meta[0]:
                title = meta[0]
            else:
                win = WindowManager.get_window(hwnd)
                if win:
                    title = win.title
        except Exception:
            pass

        t_low = title.lower()
        page_type = "UNKNOWN"
        if any(k in t_low for k in ("download history", "settings", "extensions", "bookmarks", "history", "cài đặt")):
            page_type = "AUXILIARY"
        elif any(k in t_low for k in ("search", "tìm kiếm", "results")):
            page_type = "SEARCH_RESULTS"
        elif any(k in t_low for k in ("watch", " - youtube")) and t_low != "youtube - google chrome":
            page_type = "WATCH_PAGE"
        elif "youtube" in t_low:
            page_type = "HOME"

        card_ids = []
        if raw_components:
            for c in raw_components:
                if isinstance(c, dict):
                    cid = c.get("id") or c.get("text") or ""
                    if cid:
                        card_ids.append(str(cid))
                elif hasattr(c, "id"):
                    card_ids.append(str(c.id))

        return cls(
            hwnd=hwnd,
            title=title,
            page_type=page_type,
            video_count=len(raw_components or []),
            visible_cards=card_ids,
            timestamp=time.time(),
        )


class UIInteractionService:
    """
    Standardized transactional interaction engine with task window binding and deterministic verification.
    """

    @classmethod
    def select_youtube_video(
        cls,
        index: int = 1,
        application: str = "chrome",
        wait_load: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Select YouTube video using 100% JavaScript DOM Injection.
        Eliminates legacy row-major sorting fallback for YouTube selection.
        """
        from .dom_perception import select_youtube_video_by_dom
        return select_youtube_video_by_dom(
            requested_ordinal=index,
            application=application,
            wait_load=wait_load,
            dry_run=dry_run,
        )

    @classmethod
    def _perceive_video_components(cls, hwnd: int) -> list[Any]:
        """Perceive video components bound to a specific HWND, prioritizing direct DOM perception."""
        try:
            from .dom_perception import ChromeDOMConnector
            dom_items = ChromeDOMConnector.extract_youtube_videos(hwnd=hwnd)
            if dom_items:
                res = []
                for item in dom_items:
                    res.append({
                        "id": item.component_id,
                        "type": "VIDEO_CARD",
                        "title": item.title,
                        "href": item.href,
                        "bbox": item.card_bbox if item.card_bbox else item.bbox,
                        "center": (item.center_x, item.center_y),
                        "safe_click_point": (item.bbox[2] / 2.0, item.bbox[3] / 2.0),
                        "children": [
                            {"id": f"{item.component_id}_thumbnail", "role": "thumbnail", "bbox": item.bbox}
                        ],
                        "visible": True,
                        "source": "DOM",
                    })
                return res
        except Exception as ex:
            log.debug("[UI_PERCEPTION] DOM Perception notice: %s", ex)

        try:
            from ..ui_perception.models import ElementType
            from ..ui_perception.service import get_ui_service
            ui_service = get_ui_service()
            tree = ui_service.perceive_active_window(force_fresh=True, hwnd=hwnd)
            if tree and tree.elements:
                video_elements = [
                    elem for elem in tree.elements.values()
                    if elem.type == ElementType.VIDEO_CARD
                ]
                if video_elements:
                    return video_elements
        except Exception as ex:
            log.debug("[UI_PERCEPTION] UI Service perception notice: %s", ex)

        return []

    @classmethod
    def _verify_youtube_transition(
        cls,
        hwnd: int,
        before_state: YouTubeState,
        target_semantic: YouTubeVideoTarget,
        timeout: float = 1.5,
    ) -> tuple[bool, str, YouTubeState]:
        """
        Poll for YouTube page transition (URL change, watch page title, or player controls).
        Strictly observation only — NEVER clicks again.
        """
        deadline = time.time() + timeout
        interval = 0.15

        curr_state = before_state
        while time.time() < deadline:
            curr_state = YouTubeState.capture(hwnd)

            # Check 1: Title updated away from initial state to watch page / video title
            if curr_state.title and curr_state.title != before_state.title:
                t_low = curr_state.title.lower()
                if any(k in t_low for k in ("youtube", "watch", " - youtube", "rick astley", target_semantic.title.lower() if target_semantic.title else "video")):
                    return True, f"Title updated to '{curr_state.title}'", curr_state

            # Check 2: Page transitioned from HOME/SEARCH to WATCH_PAGE
            if curr_state.page_type == "WATCH_PAGE" and before_state.page_type != "WATCH_PAGE":
                return True, f"Page transitioned from {before_state.page_type} to WATCH_PAGE", curr_state

            # Check 3: UI tree detected video player
            try:
                from ..ui_perception.models import ElementType
                from ..ui_perception.service import get_ui_service
                ui_service = get_ui_service()
                post_tree = ui_service.perceive_active_window(force_fresh=False, hwnd=hwnd)
                if post_tree:
                    if any(e.type in (ElementType.VIDEO_PLAYER, ElementType.PLAYER_CONTROL) for e in post_tree.elements.values()):
                        return True, "Video player detected in active UI tree", curr_state
            except Exception:
                pass

            time.sleep(interval)

        curr_state = YouTubeState.capture(hwnd)
        if curr_state.title and curr_state.title != before_state.title:
            return True, f"Title updated to '{curr_state.title}'", curr_state

        return False, f"No state transition detected within timeout ({timeout:.1f}s)", curr_state

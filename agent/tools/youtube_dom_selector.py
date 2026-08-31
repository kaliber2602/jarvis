"""
youtube_dom_selector.py

Authoritative DOM-Based YouTube Card/Video Selector for Jarvis Agent.
100% DOM-driven: eliminates all legacy geometric sorting (ROW_MAJOR_SORT, y_tolerance).
Fails fast with detailed debug logs when DOM extraction returns 0 items.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Union

from .dom_perception import (
    DOMExtractionResult,
    DOMVideoItem,
    YOUTUBE_DOM_EXTRACTOR_JS,
    ChromeDOMConnector,
    select_youtube_video_by_dom,
)

log = logging.getLogger("hermes.youtube_dom_selector")


# =============================================================================
# B. Python Data Models
# =============================================================================
@dataclass(frozen=True)
class DOMCardItem:
    """Represents a validated YouTube card extracted directly from Chrome DOM."""
    ordinal: int
    component_id: str
    title: str
    href: str
    viewport_x: float  # Center X in Viewport coordinates
    viewport_y: float  # Center Y in Viewport coordinates
    bbox: list[float]  # [x, y, width, height] of thumbnail anchor in Viewport space
    card_bbox: list[float] = field(default_factory=list)
    is_ad: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class YouTubeSelectionResult:
    """Structured result returned by YouTube DOM Selector."""
    success: bool
    status: str
    ordinal: int
    component_id: str
    title: str
    href: str
    is_ad: bool
    viewport_point: tuple[float, float]
    screen_point: tuple[int, int]
    total_visible_items: int
    message: str
    coord_math: str = ""
    debug_log: list[str] = field(default_factory=list)
    click_completed: bool = False
    move_verified: bool = False


# =============================================================================
# C. YouTubeDOMSelector Core Engine
# =============================================================================
class YouTubeDOMSelector:
    """
    Authoritative DOM Perception Engine for YouTube Video Selection.
    Executes JS payload, culls off-screen elements, and maps to Physical Screen Coordinates.
    """

    @classmethod
    def set_simulation_data(cls, items: Optional[Union[dict[str, Any], list[dict[str, Any]]]]) -> None:
        """Inject mock DOM items for testing."""
        ChromeDOMConnector.set_simulated_dom_videos(items)

    @classmethod
    def extract_visible_cards(
        cls,
        browser_connector: Any = None,
        cdp_port: int = 9222,
        timeout: float = 2.0,
    ) -> list[DOMCardItem]:
        """
        Execute JavaScript extractor via connector or Chrome DevTools Protocol.
        """
        res = ChromeDOMConnector.extract_youtube_videos(
            browser_connector=browser_connector,
            cdp_port=cdp_port,
            timeout=timeout,
        )
        cards = []
        for it in res.videos:
            cards.append(DOMCardItem(
                ordinal=it.ordinal,
                component_id=it.component_id,
                title=it.title,
                href=it.href,
                viewport_x=it.center_x,
                viewport_y=it.center_y,
                bbox=it.bbox,
                card_bbox=it.card_bbox,
                is_ad=it.is_ad,
            ))
        return cards

    @classmethod
    def select_youtube_video(
        cls,
        requested_ordinal: int,
        application: str = "chrome",
        browser_connector: Any = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Main entry point: Extracts DOM items, finds the requested ordinal,
        transforms coordinates, and dispatches the physical click transaction.
        Fails fast if DOM extraction returns 0 items (NO FALLBACK).
        """
        return select_youtube_video_by_dom(
            requested_ordinal=requested_ordinal,
            application=application,
            browser_connector=browser_connector,
            dry_run=dry_run,
        )


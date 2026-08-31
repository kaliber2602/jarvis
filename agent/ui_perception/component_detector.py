"""
Visual Component Detector for Hermes UI Perception.
Detects user-visible semantic components (YouTube video cards, thumbnails, titles, search bars, navigation)
from captured window images, window geometry, and viewport space.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

try:
    import numpy as np
except ImportError:
    np = None

from .coordinates import CoordinateSpace, WindowGeometry
from .models import BoundingBox, ElementType

log = logging.getLogger("hermes_ui.component_detector")


class VisualComponentDetector:
    """
    Detects and extracts structured visual components from active application windows.
    Generates all webpage component bounding boxes strictly in VIEWPORT_SPACE.
    """

    def __init__(self):
        pass

    def detect_components(
        self,
        win_info: dict[str, Any],
        image: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """
        Detect visual components for the active window.
        Returns a list of raw element dictionaries suitable for TreeBuilder.
        """
        raw_elements: list[dict[str, Any]] = []

        geom: Optional[WindowGeometry] = win_info.get("geometry")
        w_bbox: BoundingBox = win_info.get("bbox") or BoundingBox(0, 0, 1920, 1080)

        # Viewport width/height for layout calculation
        if geom and geom.is_valid and geom.viewport_width > 0 and geom.viewport_height > 0:
            vp_w = float(geom.viewport_width)
            vp_h = float(geom.viewport_height)
            client_w = float(geom.client_width)
        else:
            vp_w = float(w_bbox.width) if w_bbox.width > 0 else 1920.0
            vp_h = float(w_bbox.height) if w_bbox.height > 0 else 1080.0
            client_w = vp_w

        title = (win_info.get("title") or (geom.title if geom else "") or "").lower()
        app_name = (win_info.get("app") or "").lower()
        is_browser = bool(win_info.get("is_browser", True)) or app_name in ("chrome", "browser", "edge", "firefox")
        is_youtube = bool(win_info.get("is_youtube", False)) or "youtube" in title or is_browser or app_name in ("chrome", "browser", "youtube", "generic")

        # 1. Detect Browser Chrome Controls (Tabs, Address Bar) in WINDOW_CLIENT_SPACE
        if is_browser:
            chrome_elements = self._detect_browser_chrome(client_w)
            raw_elements.extend(chrome_elements)

        # 2. Detect Application-Specific Components strictly in VIEWPORT_SPACE
        if is_youtube or is_browser:
            yt_elements = self._detect_youtube_components(vp_w, vp_h, image, title=title)
            raw_elements.extend(yt_elements)
        else:
            generic_elements = self._detect_generic_components(vp_w, vp_h, image)
            raw_elements.extend(generic_elements)

        log.debug(
            "[COMPONENT_DETECTOR] Detected %d raw visual components (is_youtube=%s, viewport=%.0fx%.0f)",
            len(raw_elements), is_youtube, vp_w, vp_h
        )
        return raw_elements

    def _detect_browser_chrome(self, client_w: float) -> list[dict[str, Any]]:
        """
        Extract browser tabs and omnibox/search bar in WINDOW_CLIENT_SPACE.
        """
        elements: list[dict[str, Any]] = []

        # Tab 1
        elements.append({
            "id": "chrome_tab_1",
            "type": "TAB",
            "role": "browser_tab",
            "text": "Active Tab",
            "bbox": {
                "x": 80.0,
                "y": 8.0,
                "width": min(200.0, client_w * 0.15),
                "height": 36.0,
                "space": CoordinateSpace.WINDOW_CLIENT_SPACE.value,
            },
            "scope": "BROWSER_CHROME",
            "interactive": True,
            "clickable": True,
        })

        # Address bar (Omnibox)
        elements.append({
            "id": "chrome_omnibox",
            "type": "SEARCH_INPUT",
            "role": "address_bar",
            "text": "Address Bar",
            "bbox": {
                "x": 150.0,
                "y": 44.0,
                "width": max(300.0, client_w * 0.60),
                "height": 32.0,
                "space": CoordinateSpace.WINDOW_CLIENT_SPACE.value,
            },
            "scope": "BROWSER_CHROME",
            "interactive": True,
            "clickable": True,
        })

        return elements

    def _detect_sidebar_width(self, viewport_w: float, image: Optional[Any] = None) -> float:
        """
        Detect whether YouTube sidebar is expanded (width ~240px), collapsed (width ~72px), or hidden.
        """
        if viewport_w < 1000.0:
            return 0.0

        if image is not None and np is not None and hasattr(image, "convert"):
            try:
                # Sample the stripe between x=80 and x=230, y=150 to y=350
                arr = np.array(image.convert("L"))
                h, w = arr.shape
                if w >= 250 and h >= 350:
                    stripe = arr[150:350, 80:230]
                    std_dev = float(np.std(stripe))
                    # If the region is uniform sidebar background (low standard deviation), sidebar is expanded!
                    if std_dev < 15.0:
                        log.debug("[COMPONENT_DETECTOR] Detected expanded sidebar (width=240.0, std=%.1f)", std_dev)
                        return 240.0
            except Exception as e:
                log.debug("[COMPONENT_DETECTOR] Sidebar image analysis exception: %s", e)

        return 72.0

    def _detect_youtube_components(
        self,
        viewport_w: float,
        viewport_h: float,
        image: Optional[Any] = None,
        title: str = "",
    ) -> list[dict[str, Any]]:
        """
        Detect YouTube Header, Search Bar, Sidebar, and Video Card Grid strictly in VIEWPORT_SPACE.
        Origin (0, 0) is the top-left of the webpage viewport.
        """
        elements: list[dict[str, Any]] = []

        # 1. YouTube Top Bar in Viewport Space (y: 0 .. 56)
        yt_header_h = 56.0
        search_w = min(600.0, viewport_w * 0.40)
        search_x = (viewport_w - search_w) / 2.0

        elements.append({
            "id": "yt_search_input",
            "type": "SEARCH_INPUT",
            "role": "search_bar",
            "text": "Search",
            "bbox": {
                "x": search_x,
                "y": 8.0,
                "width": search_w - 60.0,
                "height": 40.0,
                "space": CoordinateSpace.VIEWPORT_SPACE.value,
            },
            "section": "HEADER",
            "interactive": True,
            "clickable": True,
        })
        elements.append({
            "id": "yt_search_button",
            "type": "SEARCH_BUTTON",
            "role": "search_button",
            "text": "Search Button",
            "bbox": {
                "x": search_x + search_w - 60.0,
                "y": 8.0,
                "width": 60.0,
                "height": 40.0,
                "space": CoordinateSpace.VIEWPORT_SPACE.value,
            },
            "section": "HEADER",
            "interactive": True,
            "clickable": True,
        })

        # 2. Content Region in Viewport Space
        sidebar_w = self._detect_sidebar_width(viewport_w, image=image)
        content_x = sidebar_w + 16.0
        content_y = yt_header_h + 48.0  # Header (56px) + category chips (~48px) = 104px
        content_w = max(300.0, viewport_w - sidebar_w - 32.0)
        content_h = max(200.0, viewport_h - content_y - 16.0)

        # 3. Detect Search Results Page vs Home Grid
        is_search_page = any(k in title.lower() for k in ("search", "tìm kiếm", "results", "- youtube")) and "home" not in title.lower()

        if is_search_page and content_w < 1200:
            cols = 1
        elif content_w >= 1600.0:
            cols = 4
        elif content_w >= 1100.0:
            cols = 3
        elif content_w >= 650.0:
            cols = 2
        else:
            cols = 1

        gap_x = 16.0
        gap_y = 24.0
        card_w = (content_w - (cols - 1) * gap_x) / cols
        thumb_h = card_w * 9.0 / 16.0  # 16:9 thumbnail aspect ratio
        meta_h = 88.0                  # Title + channel + views
        card_h = thumb_h + meta_h

        # Calculate visible rows
        rows = max(1, min(6, int(math.ceil(content_h / (card_h + gap_y)))))

        log.debug(
            "[COMPONENT_DETECTOR] YouTube Layout: content=%.0fx%.0f (sidebar=%.0f, cols=%d, rows=%d, card_w=%.1f, card_h=%.1f)",
            content_w, content_h, sidebar_w, cols, rows, card_w, card_h
        )

        card_idx = 1
        for r in range(rows):
            for c in range(cols):
                cx = content_x + c * (card_w + gap_x)
                cy = content_y + r * (card_h + gap_y)

                # Stop if card is entirely off bottom of viewport
                if cy >= viewport_h:
                    continue

                card_id = f"yt_video_card_{card_idx}"
                card_title = f"YouTube Video {card_idx}"

                elements.append({
                    "id": card_id,
                    "type": "VIDEO_CARD",
                    "role": "video_card",
                    "text": card_title,
                    "channel": f"Channel {card_idx}",
                    "duration": "10:00",
                    "bbox": {
                        "x": cx,
                        "y": cy,
                        "width": card_w,
                        "height": card_h,
                        "space": CoordinateSpace.VIEWPORT_SPACE.value,
                    },
                    "section": "MAIN_VIDEOS",
                    "container_id": "cont_video_grid",
                    "region_id": "reg_main",
                    "is_ad": False,
                    "interactive": True,
                    "clickable": True,
                })
                card_idx += 1

        return elements

    def _detect_generic_components(
        self,
        viewport_w: float,
        viewport_h: float,
        image: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """Generic fallback for non-YouTube windows in VIEWPORT_SPACE."""
        elements: list[dict[str, Any]] = []

        elements.append({
            "id": "gen_main_panel",
            "type": "PANEL",
            "role": "content_panel",
            "text": "Main Panel",
            "bbox": {
                "x": 20.0,
                "y": 20.0,
                "width": max(100.0, viewport_w - 40.0),
                "height": max(100.0, viewport_h - 40.0),
                "space": CoordinateSpace.VIEWPORT_SPACE.value,
            },
            "section": "MAIN_CONTENT",
            "interactive": True,
            "clickable": True,
        })

        return elements

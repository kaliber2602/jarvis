"""
Region Detection and Scope Partitioning Engine.
Identifies major regions (Header, Sidebar, Main, Right Panel, Modals, Overlays, Browser Chrome)
and assigns containment boundaries, Z-order, and interaction blocking priorities.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .models import BoundingBox, RegionType, UIRegion, VisibilityState

log = logging.getLogger("hermes_ui.region_detector")


class RegionDetector:
    """
    Partitions the window or screen into structured semantic regions.
    """

    def __init__(self):
        pass

    def detect_regions(
        self,
        window_bbox: BoundingBox,
        is_browser: bool = True,
        is_youtube: bool = False,
        known_elements: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, UIRegion]:
        """
        Partition viewport into major regions based on window geometry, application layout rules,
        and visual element clustering.
        """
        regions: dict[str, UIRegion] = {}
        w = window_bbox.width
        h = window_bbox.height
        ox = window_bbox.x
        oy = window_bbox.y

        # 1. Base Screen / Window Region
        regions["reg_window"] = UIRegion(
            id="reg_window",
            type=RegionType.WINDOW,
            bbox=BoundingBox(ox, oy, w, h),
            scope="WINDOW",
            z_order=0,
            visibility=VisibilityState.VISIBLE,
        )

        # 2. Browser Chrome vs Webpage Partitioning
        webpage_top_offset = 0.0
        if is_browser:
            chrome_height = 0.09 * h  # Typical Chrome tab bar + Omnibox
            regions["reg_browser_chrome"] = UIRegion(
                id="reg_browser_chrome",
                type=RegionType.BROWSER_CHROME,
                bbox=BoundingBox(ox, oy, w, chrome_height),
                scope="BROWSER_CHROME",
                parent_id="reg_window",
                z_order=10,
                visibility=VisibilityState.VISIBLE,
            )
            webpage_top_offset = chrome_height

        webpage_height = h - webpage_top_offset
        regions["reg_webpage"] = UIRegion(
            id="reg_webpage",
            type=RegionType.WEBPAGE,
            bbox=BoundingBox(ox, oy + webpage_top_offset, w, webpage_height),
            scope="WEBPAGE",
            parent_id="reg_window",
            z_order=1,
            visibility=VisibilityState.VISIBLE,
            scroll_context="PAGE_SCROLL",
        )

        # 3. Check for any Blocking Overlays / Modals in known elements
        has_blocking_modal = False
        if known_elements:
            for elem in known_elements:
                elem_type = str(elem.get("type", "")).upper()
                if elem_type in ("MODAL", "DIALOG", "OVERLAY", "BLOCKING_DIALOG", "RESTORE_PAGES_POPUP"):
                    ebbox = elem.get("bbox")
                    if isinstance(ebbox, dict):
                        m_bbox = BoundingBox(
                            ebbox.get("x", ox + w * 0.25),
                            ebbox.get("y", oy + h * 0.2),
                            ebbox.get("width", w * 0.5),
                            ebbox.get("height", h * 0.4),
                        )
                    else:
                        m_bbox = BoundingBox(ox + w * 0.25, oy + h * 0.2, w * 0.5, h * 0.4)

                    m_id = f"reg_modal_{len(regions)}"
                    regions[m_id] = UIRegion(
                        id=m_id,
                        type=RegionType.MODAL,
                        bbox=m_bbox,
                        scope="OVERLAY",
                        parent_id="reg_window",
                        z_order=100,
                        visibility=VisibilityState.VISIBLE,
                        is_blocking=True,
                    )
                    has_blocking_modal = True

        # 4. Standard Webpage Sub-Regions (Header, Sidebar, Main Content, Right Panel)
        wp_y = oy + webpage_top_offset
        header_height = 0.08 * webpage_height
        sidebar_width = 0.15 * w

        # Header (Top Bar inside Webpage)
        regions["reg_header"] = UIRegion(
            id="reg_header",
            type=RegionType.HEADER,
            bbox=BoundingBox(ox, wp_y, w, header_height),
            scope="WEBPAGE",
            parent_id="reg_webpage",
            z_order=5,
            visibility=VisibilityState.VISIBLE,
        )

        content_y = wp_y + header_height
        content_height = webpage_height - header_height

        # Sidebar (Left Navigation)
        regions["reg_sidebar"] = UIRegion(
            id="reg_sidebar",
            type=RegionType.SIDEBAR,
            bbox=BoundingBox(ox, content_y, sidebar_width, content_height),
            scope="WEBPAGE",
            parent_id="reg_webpage",
            z_order=2,
            visibility=VisibilityState.VISIBLE,
            scroll_context="SIDEBAR_SCROLL",
        )

        # Determine if there is a Right Panel (e.g. Playlist / Watch Page)
        has_right_panel = False
        if known_elements:
            for elem in known_elements:
                sec = str(elem.get("section", "")).lower()
                reg = str(elem.get("region", "")).lower()
                if "playlist" in sec or "right" in reg or "side_panel" in reg:
                    has_right_panel = True
                    break

        main_x = ox + sidebar_width
        if has_right_panel:
            main_width = 0.58 * w
            right_panel_x = main_x + main_width
            right_panel_width = w - (sidebar_width + main_width)

            # Main Player / Content
            regions["reg_main"] = UIRegion(
                id="reg_main",
                type=RegionType.MAIN_CONTENT,
                bbox=BoundingBox(main_x, content_y, main_width, content_height),
                scope="WEBPAGE",
                parent_id="reg_webpage",
                z_order=2,
                visibility=VisibilityState.VISIBLE,
                scroll_context="PAGE_SCROLL",
            )

            # Right Panel (Playlist / Related)
            regions["reg_right_panel"] = UIRegion(
                id="reg_right_panel",
                type=RegionType.RIGHT_PANEL,
                bbox=BoundingBox(right_panel_x, content_y, right_panel_width, content_height),
                scope="WEBPAGE",
                parent_id="reg_webpage",
                z_order=3,
                visibility=VisibilityState.VISIBLE,
                scroll_context="PLAYLIST_SCROLL",
            )
        else:
            main_width = w - sidebar_width
            regions["reg_main"] = UIRegion(
                id="reg_main",
                type=RegionType.MAIN_CONTENT,
                bbox=BoundingBox(main_x, content_y, main_width, content_height),
                scope="WEBPAGE",
                parent_id="reg_webpage",
                z_order=2,
                visibility=VisibilityState.VISIBLE,
                scroll_context="PAGE_SCROLL",
            )

        log.debug(
            "[REGION_DETECTOR] Partitioned window into %d regions (Blocking Modal: %s)",
            len(regions), has_blocking_modal
        )
        return regions

    def get_region_for_point(self, point: Point, regions: dict[str, UIRegion]) -> Optional[UIRegion]:
        """
        Find the topmost region covering a point, respecting Z-Order.
        """
        matching: list[UIRegion] = []
        for r in regions.values():
            if r.bbox.contains_point(point) and r.visibility == VisibilityState.VISIBLE:
                matching.append(r)

        if not matching:
            return None

        # Sort by z_order descending, then area ascending (more specific sub-region first)
        matching.sort(key=lambda r: (-r.z_order, r.bbox.area))
        return matching[0]

    def get_region_for_bbox(self, bbox: BoundingBox, regions: dict[str, UIRegion]) -> Optional[UIRegion]:
        """
        Find the most specific region enclosing or intersecting the bbox.
        """
        return self.get_region_for_point(bbox.center, regions)

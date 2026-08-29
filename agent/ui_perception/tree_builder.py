"""
Semantic UI Tree Builder.
Synthesizes regions, layout containers, composite components, and elements
into a unified hierarchical Semantic Tree.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Sequence

from .composite_builder import CompositeBuilder
from .layout_engine import LayoutEngine
from .models import (
    BoundingBox,
    CompositeComponent,
    ElementType,
    LayoutType,
    RegionType,
    UIContainer,
    UIElement,
    UIRegion,
    UITree,
    VisibilityState,
)
from .region_detector import RegionDetector

log = logging.getLogger("hermes_ui.tree_builder")


class TreeBuilder:
    """
    Constructs the Semantic UI Tree with hierarchical containment and ordering contexts.
    """

    def __init__(self):
        self.region_detector = RegionDetector()
        self.layout_engine = LayoutEngine()
        self.composite_builder = CompositeBuilder()

    def build_tree(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        window_title: str = "",
        app_name: str = "chrome",
        is_browser: bool = True,
        is_youtube: bool = False,
        stability_score: float = 1.0,
        raw_elements_data: Optional[list[dict[str, Any]]] = None,
    ) -> UITree:
        """
        Build complete Semantic UI Tree.
        """
        window_bbox = BoundingBox(0, 0, screen_width, screen_height)

        tree = UITree(
            screen_width=screen_width,
            screen_height=screen_height,
            window_title=window_title,
            app_name=app_name,
            is_browser=is_browser,
            timestamp=time.time(),
            stability_score=stability_score,
        )

        # 1. Detect Regions
        regions = self.region_detector.detect_regions(
            window_bbox=window_bbox,
            is_browser=is_browser,
            is_youtube=is_youtube,
            known_elements=raw_elements_data,
        )
        tree.regions = regions

        # 2. Process Raw Element Data / Synth Components
        containers_map: dict[str, UIContainer] = {}
        elements_map: dict[str, UIElement] = {}
        composites_map: dict[str, CompositeComponent] = {}

        # Default standard containers
        main_reg = regions.get("reg_main")
        main_reg_id = main_reg.id if main_reg else "reg_window"
        main_bbox = main_reg.bbox if main_reg else window_bbox

        sidebar_reg = regions.get("reg_sidebar")
        sidebar_reg_id = sidebar_reg.id if sidebar_reg else "reg_window"
        sidebar_bbox = sidebar_reg.bbox if sidebar_reg else BoundingBox(0, 0, screen_width * 0.15, screen_height)

        right_reg = regions.get("reg_right_panel")
        right_reg_id = right_reg.id if right_reg else main_reg_id

        # Container: Video Grid
        cont_video_grid = UIContainer(
            id="cont_video_grid",
            region_id=main_reg_id,
            layout_type=LayoutType.GRID,
            bbox=main_bbox,
            name="Video Grid",
            section_name="MAIN_VIDEOS",
            scrollable=True,
            scroll_type="PAGE_SCROLL",
        )
        containers_map[cont_video_grid.id] = cont_video_grid

        # Container: Shorts Grid
        cont_shorts = UIContainer(
            id="cont_shorts_grid",
            region_id=main_reg_id,
            layout_type=LayoutType.HORIZONTAL_LIST,
            bbox=BoundingBox(main_bbox.x, main_bbox.y + main_bbox.height * 0.5, main_bbox.width, main_bbox.height * 0.4),
            name="Shorts Carousel",
            section_name="SHORTS",
        )
        containers_map[cont_shorts.id] = cont_shorts

        # Container: Playlist
        cont_playlist = UIContainer(
            id="cont_playlist",
            region_id=right_reg_id,
            layout_type=LayoutType.VERTICAL_LIST,
            bbox=right_reg.bbox if right_reg else main_bbox,
            name="Playlist Container",
            section_name="PLAYLIST",
            scrollable=True,
            scroll_type="PLAYLIST_SCROLL",
        )
        containers_map[cont_playlist.id] = cont_playlist

        # Container: Sidebar Menu
        cont_sidebar = UIContainer(
            id="cont_sidebar_menu",
            region_id=sidebar_reg_id,
            layout_type=LayoutType.SIDEBAR,
            bbox=sidebar_bbox,
            name="Sidebar Navigation",
            section_name="SIDEBAR",
            scrollable=True,
            scroll_type="SIDEBAR_SCROLL",
        )
        containers_map[cont_sidebar.id] = cont_sidebar

        # 3. Instantiate Elements from raw_elements_data if provided
        grouped_elements: dict[str, list[UIElement]] = {}

        if raw_elements_data:
            for item in raw_elements_data:
                e_id = str(item.get("id", f"elem_{len(elements_map)}"))
                e_type_str = str(item.get("type", "BUTTON")).upper()
                try:
                    e_type = ElementType(e_type_str)
                except ValueError:
                    e_type = ElementType.BUTTON

                # Determine BoundingBox
                raw_bbox = item.get("bbox")
                if isinstance(raw_bbox, dict):
                    bbox = BoundingBox(
                        x=float(raw_bbox.get("x", 0)),
                        y=float(raw_bbox.get("y", 0)),
                        width=float(raw_bbox.get("width", 100)),
                        height=float(raw_bbox.get("height", 50)),
                    )
                elif isinstance(raw_bbox, (tuple, list)) and len(raw_bbox) == 4:
                    bbox = BoundingBox(float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3]))
                else:
                    bbox = BoundingBox(0, 0, 100, 50)

                text_val = str(item.get("text", "")).strip()
                is_ad = item.get("is_ad", False) or self.composite_builder.is_advertisement_text(text_val)

                # Scope assignment
                scope_val = item.get("scope")
                if not scope_val:
                    if item.get("role") in ("browser_tab", "omnibox", "address_bar") or "chrome" in item.get("id", "").lower():
                        scope_val = "BROWSER_CHROME"
                    else:
                        scope_val = "WEBPAGE"

                # Container & Region routing
                sec_name = str(item.get("section", "")).upper()
                c_id = item.get("container_id")

                if not c_id:
                    if "SHORT" in sec_name or e_type == ElementType.SHORT_CARD:
                        c_id = "cont_shorts_grid"
                    elif "PLAYLIST" in sec_name or e_type == ElementType.PLAYLIST_ITEM:
                        c_id = "cont_playlist"
                    elif "SIDEBAR" in sec_name or e_type == ElementType.SIDEBAR_ITEM:
                        c_id = "cont_sidebar_menu"
                    elif scope_val == "BROWSER_CHROME":
                        c_id = "cont_chrome"
                    else:
                        c_id = "cont_video_grid"

                r_id = item.get("region_id")
                if not r_id:
                    if c_id == "cont_playlist":
                        r_id = right_reg_id
                    elif c_id == "cont_sidebar_menu":
                        r_id = sidebar_reg_id
                    elif scope_val == "BROWSER_CHROME":
                        r_id = "reg_browser_chrome"
                    else:
                        r_id = main_reg_id

                is_offscreen = bool(item.get("offscreen")) or (bbox.top >= screen_height) or (bbox.bottom <= 0) or (bbox.left >= screen_width) or (bbox.right <= 0)
                vis_state = VisibilityState.OFFSCREEN if is_offscreen else VisibilityState.VISIBLE

                # Build Composite or Atomic Element
                if e_type == ElementType.VIDEO_CARD:
                    comp = self.composite_builder.build_video_card(
                        card_id=e_id,
                        bbox=bbox,
                        title_text=text_val,
                        channel_name=item.get("channel", ""),
                        duration_text=item.get("duration", ""),
                        is_advertisement=is_ad,
                        container_id=c_id,
                        region_id=r_id,
                    )
                    comp.raw_element.visibility = vis_state
                    for ch in comp.raw_element.children:
                        ch.visibility = vis_state
                    composites_map[comp.id] = comp
                    elements_map[comp.raw_element.id] = comp.raw_element
                    for ch in comp.raw_element.children:
                        elements_map[ch.id] = ch
                    grouped_elements.setdefault(c_id, []).append(comp.raw_element)

                elif e_type == ElementType.SHORT_CARD:
                    comp = self.composite_builder.build_short_card(
                        card_id=e_id,
                        bbox=bbox,
                        title_text=text_val,
                        container_id=c_id,
                        region_id=r_id,
                    )
                    comp.raw_element.visibility = vis_state
                    for ch in comp.raw_element.children:
                        ch.visibility = vis_state
                    composites_map[comp.id] = comp
                    elements_map[comp.raw_element.id] = comp.raw_element
                    for ch in comp.raw_element.children:
                        elements_map[ch.id] = ch
                    grouped_elements.setdefault(c_id, []).append(comp.raw_element)

                elif e_type == ElementType.PLAYLIST_ITEM:
                    comp = self.composite_builder.build_playlist_item(
                        item_id=e_id,
                        bbox=bbox,
                        title_text=text_val,
                        index_label=int(item.get("index", len(grouped_elements.get(c_id, [])) + 1)),
                        duration_text=item.get("duration", ""),
                        container_id=c_id,
                        region_id=r_id,
                    )
                    comp.raw_element.visibility = vis_state
                    for ch in comp.raw_element.children:
                        ch.visibility = vis_state
                    composites_map[comp.id] = comp
                    elements_map[comp.raw_element.id] = comp.raw_element
                    for ch in comp.raw_element.children:
                        elements_map[ch.id] = ch
                    grouped_elements.setdefault(c_id, []).append(comp.raw_element)

                elif e_type == ElementType.SIDEBAR_ITEM:
                    comp = self.composite_builder.build_sidebar_item(
                        item_id=e_id,
                        bbox=bbox,
                        label_text=text_val,
                        container_id=c_id,
                        region_id=r_id,
                    )
                    comp.raw_element.visibility = vis_state
                    for ch in comp.raw_element.children:
                        ch.visibility = vis_state
                    composites_map[comp.id] = comp
                    elements_map[comp.raw_element.id] = comp.raw_element
                    for ch in comp.raw_element.children:
                        elements_map[ch.id] = ch
                    grouped_elements.setdefault(c_id, []).append(comp.raw_element)

                else:
                    # Atomic UI Element
                    elem = UIElement(
                        id=e_id,
                        type=e_type,
                        semantic_role=item.get("role", e_type_str.lower()),
                        bbox=bbox,
                        text=text_val,
                        normalized_text=text_val.lower(),
                        container_id=c_id,
                        region_id=r_id,
                        scope=scope_val,
                        section_id=sec_name,
                        visibility=vis_state,
                        is_advertisement=is_ad,
                        interactive=item.get("interactive", True),
                        clickable=item.get("clickable", True),
                    )
                    elements_map[elem.id] = elem
                    grouped_elements.setdefault(c_id, []).append(elem)

        # 4. Layout & Visual Ordering within Each Container
        for c_id, cont_elems in grouped_elements.items():
            cont = containers_map.get(c_id)
            if not cont:
                cont = UIContainer(
                    id=c_id,
                    region_id=main_reg_id,
                    layout_type=LayoutType.UNKNOWN,
                    bbox=window_bbox,
                    name=c_id,
                )
                containers_map[c_id] = cont

            # Organize elements in container
            ordered_elems = self.layout_engine.organize_container_elements(cont, cont_elems)
            tree.visual_groups[c_id] = [e.id for e in ordered_elems]

            # Propagate visual index & row/col to composite components
            for elem in ordered_elems:
                if elem.id in composites_map:
                    comp = composites_map[elem.id]
                    comp.visual_index = elem.visual_index
                    comp.row = elem.row
                    comp.column = elem.column

        # 5. Populate Tree Collections
        tree.containers = containers_map
        tree.elements = elements_map
        tree.composites = composites_map

        # 6. Global Reading & Interaction Ordering
        # Separate reading order (all text & info) and interaction order (clickable targets)
        reading: list[str] = []
        interaction: list[str] = []

        # Order by regions first: Header -> Sidebar -> Main Content -> Right Panel
        region_order = ["reg_header", "reg_sidebar", "reg_main", "reg_right_panel"]
        for r_id in region_order:
            for c_id, cont in containers_map.items():
                if cont.region_id == r_id:
                    for e_id in tree.visual_groups.get(c_id, []):
                        reading.append(e_id)
                        elem = elements_map.get(e_id)
                        if elem and elem.clickable:
                            interaction.append(e_id)

        tree.reading_order = reading
        tree.interaction_order = interaction

        log.debug(
            "[TREE_BUILDER] Constructed UITree with %d regions, %d containers, %d elements, %d composites",
            len(tree.regions), len(tree.containers), len(tree.elements), len(tree.composites)
        )
        return tree

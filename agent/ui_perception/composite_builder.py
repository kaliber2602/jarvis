"""
Composite Component Builder and Classifier.
Aggregates atomic UI elements into high-level semantic components
(Video Card, Playlist, Sidebar Item, Search Bar, Modal Dialog, Advertisement).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .models import (
    ActionType,
    BoundingBox,
    CompositeComponent,
    ElementType,
    UIElement,
    VisibilityState,
)

log = logging.getLogger("hermes_ui.composite_builder")


class CompositeBuilder:
    """
    Builds composite semantic components and manages sub-part hierarchies.
    """

    AD_KEYWORDS = {
        "ad", "ads", "advertisement", "sponsored", "promoted", "được tài trợ", "quảng cáo"
    }

    def __init__(self):
        pass

    def is_advertisement_text(self, text: str) -> bool:
        cleaned = text.strip().lower()
        if cleaned in self.AD_KEYWORDS:
            return True
        for kw in self.AD_KEYWORDS:
            if kw in cleaned and len(cleaned) < 25:
                return True
        return False

    def build_video_card(
        self,
        card_id: str,
        bbox: BoundingBox,
        title_text: str = "",
        channel_name: str = "",
        duration_text: str = "",
        is_advertisement: bool = False,
        container_id: str = "cont_video_grid",
        region_id: str = "reg_main",
    ) -> CompositeComponent:
        """
        Synthesize a full VideoCard composite component with its constituent sub-parts.
        """
        # 1. Main Card Element
        card_elem = UIElement(
            id=card_id,
            type=ElementType.VIDEO_CARD,
            semantic_role="video_card",
            bbox=bbox,
            text=title_text,
            normalized_text=title_text.lower(),
            container_id=container_id,
            region_id=region_id,
            is_advertisement=is_advertisement,
            interactive=True,
            clickable=True,
        )

        # 2. Thumbnail sub-element (Top ~65% of card)
        thumb_h = bbox.height * 0.65
        thumb_bbox = BoundingBox(bbox.x, bbox.y, bbox.width, thumb_h)
        thumb_elem = UIElement(
            id=f"{card_id}_thumb",
            type=ElementType.THUMBNAIL,
            semantic_role="thumbnail",
            bbox=thumb_bbox,
            parent_id=card_id,
            container_id=container_id,
            region_id=region_id,
            interactive=True,
            clickable=True,
        )

        # 3. Title sub-element (Below thumbnail, left side)
        title_y = bbox.y + thumb_h + 4
        title_w = bbox.width * 0.82
        title_h = bbox.height * 0.20
        title_bbox = BoundingBox(bbox.x, title_y, title_w, title_h)
        title_elem = UIElement(
            id=f"{card_id}_title",
            type=ElementType.TITLE,
            semantic_role="title",
            bbox=title_bbox,
            text=title_text,
            normalized_text=title_text.lower(),
            parent_id=card_id,
            container_id=container_id,
            region_id=region_id,
            interactive=True,
            clickable=True,
        )

        # 4. More Button (⋮ 3-dots icon) (Below thumbnail, right side)
        more_btn_w = bbox.width * 0.15
        more_btn_x = bbox.x + bbox.width - more_btn_w
        more_btn_bbox = BoundingBox(more_btn_x, title_y, more_btn_w, title_h)
        more_elem = UIElement(
            id=f"{card_id}_more_btn",
            type=ElementType.MORE_BUTTON,
            semantic_role="more_button",
            bbox=more_btn_bbox,
            text="⋮",
            parent_id=card_id,
            container_id=container_id,
            region_id=region_id,
            interactive=True,
            clickable=True,
        )

        # 5. Channel & Duration Metadata
        channel_elem = None
        if channel_name:
            chan_y = title_y + title_h
            chan_bbox = BoundingBox(bbox.x, chan_y, title_w, bbox.height * 0.12)
            channel_elem = UIElement(
                id=f"{card_id}_chan",
                type=ElementType.CHANNEL,
                semantic_role="channel",
                bbox=chan_bbox,
                text=channel_name,
                parent_id=card_id,
                container_id=container_id,
                region_id=region_id,
            )

        duration_elem = None
        if duration_text:
            dur_w = bbox.width * 0.25
            dur_h = bbox.height * 0.10
            dur_bbox = BoundingBox(bbox.right - dur_w - 4, thumb_bbox.bottom - dur_h - 4, dur_w, dur_h)
            duration_elem = UIElement(
                id=f"{card_id}_dur",
                type=ElementType.DURATION_BADGE,
                semantic_role="duration",
                bbox=dur_bbox,
                text=duration_text,
                parent_id=card_id,
                container_id=container_id,
                region_id=region_id,
            )

        # Link children to parent
        children = [thumb_elem, title_elem, more_elem]
        if channel_elem:
            children.append(channel_elem)
        if duration_elem:
            children.append(duration_elem)
        card_elem.children = children

        card_elem.interaction_targets = {
            "thumbnail": thumb_bbox,
            "title": title_bbox,
            "more_button": more_btn_bbox,
            "primary": thumb_bbox,
        }

        composite = CompositeComponent(
            id=card_id,
            type=ElementType.VIDEO_CARD,
            container_id=container_id,
            bbox=bbox,
            is_advertisement=is_advertisement,
            thumbnail=thumb_elem,
            title=title_elem,
            channel=channel_elem,
            duration=duration_elem,
            more_button=more_elem,
            raw_element=card_elem,
        )
        return composite

    def build_short_card(
        self,
        card_id: str,
        bbox: BoundingBox,
        title_text: str = "",
        view_count: str = "",
        container_id: str = "cont_shorts_grid",
        region_id: str = "reg_main",
    ) -> CompositeComponent:
        """
        Synthesize a YouTube Shorts card.
        """
        card_elem = UIElement(
            id=card_id,
            type=ElementType.SHORT_CARD,
            semantic_role="short_card",
            bbox=bbox,
            text=title_text,
            normalized_text=title_text.lower(),
            container_id=container_id,
            region_id=region_id,
            section_id="SHORTS",
            interactive=True,
            clickable=True,
        )

        thumb_h = bbox.height * 0.8
        thumb_bbox = BoundingBox(bbox.x, bbox.y, bbox.width, thumb_h)
        thumb_elem = UIElement(
            id=f"{card_id}_thumb",
            type=ElementType.THUMBNAIL,
            bbox=thumb_bbox,
            parent_id=card_id,
            container_id=container_id,
            region_id=region_id,
            section_id="SHORTS",
        )

        title_y = bbox.y + thumb_h + 2
        title_bbox = BoundingBox(bbox.x, title_y, bbox.width, bbox.height * 0.18)
        title_elem = UIElement(
            id=f"{card_id}_title",
            type=ElementType.TITLE,
            bbox=title_bbox,
            text=title_text,
            parent_id=card_id,
            container_id=container_id,
            region_id=region_id,
            section_id="SHORTS",
        )

        card_elem.children = [thumb_elem, title_elem]
        card_elem.interaction_targets = {
            "thumbnail": thumb_bbox,
            "title": title_bbox,
            "primary": thumb_bbox,
        }

        return CompositeComponent(
            id=card_id,
            type=ElementType.SHORT_CARD,
            container_id=container_id,
            bbox=bbox,
            thumbnail=thumb_elem,
            title=title_elem,
            raw_element=card_elem,
        )

    def build_playlist_item(
        self,
        item_id: str,
        bbox: BoundingBox,
        title_text: str = "",
        index_label: int = 1,
        duration_text: str = "",
        container_id: str = "cont_playlist",
        region_id: str = "reg_right_panel",
    ) -> CompositeComponent:
        """
        Synthesize a Playlist Item row (Index number, thumbnail, title, duration).
        """
        item_elem = UIElement(
            id=item_id,
            type=ElementType.PLAYLIST_ITEM,
            semantic_role="playlist_item",
            bbox=bbox,
            text=title_text,
            normalized_text=title_text.lower(),
            container_id=container_id,
            region_id=region_id,
            section_id="PLAYLIST",
            interactive=True,
            clickable=True,
        )

        # Index label (left 10%)
        idx_w = bbox.width * 0.10
        idx_elem = UIElement(
            id=f"{item_id}_idx",
            type=ElementType.TEXT,
            bbox=BoundingBox(bbox.x, bbox.y, idx_w, bbox.height),
            text=str(index_label),
            parent_id=item_id,
        )

        # Thumbnail (middle left 35%)
        thumb_x = bbox.x + idx_w + 2
        thumb_w = bbox.width * 0.35
        thumb_elem = UIElement(
            id=f"{item_id}_thumb",
            type=ElementType.THUMBNAIL,
            bbox=BoundingBox(thumb_x, bbox.y + 2, thumb_w, bbox.height - 4),
            parent_id=item_id,
        )

        # Title (remaining right 55%)
        title_x = thumb_x + thumb_w + 4
        title_w = bbox.width - (title_x - bbox.x) - 4
        title_elem = UIElement(
            id=f"{item_id}_title",
            type=ElementType.TITLE,
            bbox=BoundingBox(title_x, bbox.y + 2, title_w, bbox.height - 4),
            text=title_text,
            parent_id=item_id,
        )

        item_elem.children = [idx_elem, thumb_elem, title_elem]
        item_elem.interaction_targets = {
            "thumbnail": thumb_elem.bbox,
            "title": title_elem.bbox,
            "primary": item_elem.bbox,
        }

        return CompositeComponent(
            id=item_id,
            type=ElementType.PLAYLIST_ITEM,
            container_id=container_id,
            bbox=bbox,
            thumbnail=thumb_elem,
            title=title_elem,
            raw_element=item_elem,
        )

    def build_sidebar_item(
        self,
        item_id: str,
        bbox: BoundingBox,
        label_text: str,
        container_id: str = "cont_sidebar_menu",
        region_id: str = "reg_sidebar",
    ) -> CompositeComponent:
        """
        Synthesize a Sidebar Item (Icon + Label text).
        """
        item_elem = UIElement(
            id=item_id,
            type=ElementType.SIDEBAR_ITEM,
            semantic_role="sidebar_item",
            bbox=bbox,
            text=label_text,
            normalized_text=label_text.lower(),
            container_id=container_id,
            region_id=region_id,
            section_id="SIDEBAR",
            interactive=True,
            clickable=True,
        )

        icon_w = bbox.height * 0.7
        icon_elem = UIElement(
            id=f"{item_id}_icon",
            type=ElementType.ICON,
            bbox=BoundingBox(bbox.x + 8, bbox.y + (bbox.height - icon_w) / 2, icon_w, icon_w),
            parent_id=item_id,
        )

        label_x = bbox.x + icon_w + 16
        label_w = bbox.width - (label_x - bbox.x) - 8
        label_elem = UIElement(
            id=f"{item_id}_label",
            type=ElementType.TEXT,
            bbox=BoundingBox(label_x, bbox.y, label_w, bbox.height),
            text=label_text,
            parent_id=item_id,
        )

        item_elem.children = [icon_elem, label_elem]
        item_elem.interaction_targets = {"primary": bbox}

        return CompositeComponent(
            id=item_id,
            type=ElementType.SIDEBAR_ITEM,
            container_id=container_id,
            bbox=bbox,
            title=label_elem,
            raw_element=item_elem,
        )

"""
Component Target Abstraction & Geometry-Based Row-Major Ordering Subsystem.
Defines ComponentTarget as a first-class object and enforces deterministic,
human-like row-major ordering (Top -> Bottom, Left -> Right) independent of detector output order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Optional, Sequence

from ..ui_perception.models import BoundingBox as UIBoundingBox, Point as UIPoint, SafeClickRegion
from .coordinate_mapper import BoundingBox, Point

log = logging.getLogger("hermes.component_target")


@dataclass(frozen=True)
class ComponentTarget:
    """
    First-class immutable component target representing a concrete, validated interactable UI element.
    """
    component_id: str
    component_type: str
    bbox: tuple[float, float, float, float]  # (x, y, width, height) in viewport space
    center: tuple[float, float]              # (center_x, center_y) in viewport space
    safe_click_point: tuple[float, float]    # (x, y) in component local space
    ordinal: int | None = None               # 1-based row-major visual ordinal
    row: int = -1                            # 0-based visual row index
    column: int = -1                         # 0-based visual column index
    confidence: float = 1.0
    source: str = "CV"
    text: str = ""
    window_hwnd: int = 0

    @property
    def left(self) -> float:
        return self.bbox[0]

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def width(self) -> float:
        return self.bbox[2]

    @property
    def height(self) -> float:
        return self.bbox[3]

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def hit_test(self, viewport_point: tuple[float, float]) -> bool:
        """Check if an absolute point in viewport space falls strictly inside this component's bounding box."""
        vx, vy = viewport_point
        return (self.left <= vx <= self.right and self.top <= vy <= self.bottom)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type,
            "bbox": self.bbox,
            "center": self.center,
            "safe_click_point": self.safe_click_point,
            "ordinal": self.ordinal,
            "row": self.row,
            "column": self.column,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "text": self.text,
            "window_hwnd": self.window_hwnd,
        }


@dataclass(frozen=True)
class YouTubeVideoTarget:
    """
    First-class Semantic YouTube Video Target with rich metadata, clickable region, and source HWND binding.
    """
    ordinal: int
    component_id: str
    bbox: tuple[float, float, float, float]
    safe_click_point: tuple[float, float]
    source_hwnd: int = 0
    title: str = ""
    video_url: str = ""
    channel: str = ""
    duration: str = ""
    clickable_region: tuple[float, float, float, float] | None = None
    clickable_child_id: str | None = None

    @property
    def left(self) -> float:
        return self.bbox[0]

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def width(self) -> float:
        return self.bbox[2]

    @property
    def height(self) -> float:
        return self.bbox[3]

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def hit_test(self, viewport_point: tuple[float, float]) -> bool:
        vx, vy = viewport_point
        return (self.left <= vx <= self.right and self.top <= vy <= self.bottom)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "component_id": self.component_id,
            "bbox": self.bbox,
            "safe_click_point": self.safe_click_point,
            "source_hwnd": self.source_hwnd,
            "title": self.title,
            "video_url": self.video_url,
            "channel": self.channel,
            "duration": self.duration,
            "clickable_region": self.clickable_region,
            "clickable_child_id": self.clickable_child_id,
        }


def build_safe_click_region(
    component_or_bbox: Any,
    component_type: str = "youtube_video",
) -> SafeClickRegion:
    """
    Constructs a deterministic SafeClickRegion for a UI component.
    Isolates the safe clickable core (thumbnail / main content) while identifying
    and excluding border margins, duration badges, 3-dot menus, and action buttons.
    """
    c_id = "comp"
    children = []
    if isinstance(component_or_bbox, dict):
        bbox_raw = component_or_bbox.get("bbox")
        c_id = str(component_or_bbox.get("id") or component_or_bbox.get("component_id") or "comp")
        children = component_or_bbox.get("children", [])
        if isinstance(bbox_raw, (tuple, list)) and len(bbox_raw) >= 4:
            bx, by, bw, bh = float(bbox_raw[0]), float(bbox_raw[1]), float(bbox_raw[2]), float(bbox_raw[3])
        elif isinstance(bbox_raw, dict):
            bx = float(bbox_raw.get("x", 0))
            by = float(bbox_raw.get("y", 0))
            bw = float(bbox_raw.get("width", 442))
            bh = float(bbox_raw.get("height", 336))
        else:
            bx, by, bw, bh = 0.0, 0.0, 442.0, 336.0
    elif isinstance(component_or_bbox, (tuple, list)) and len(component_or_bbox) >= 4:
        bx, by, bw, bh = float(component_or_bbox[0]), float(component_or_bbox[1]), float(component_or_bbox[2]), float(component_or_bbox[3])
    else:
        bx, by, bw, bh = 0.0, 0.0, 442.0, 336.0

    comp_bbox = UIBoundingBox(bx, by, bw, bh)

    # Excluded child regions in local coordinates
    excluded: list[UIBoundingBox] = []
    semantic_child_pt: Optional[tuple[float, float]] = None
    semantic_child_id: Optional[str] = None

    for ch in children:
        if isinstance(ch, dict):
            ch_role = (ch.get("role") or ch.get("type") or "").lower()
            ch_b = ch.get("bbox")
            if isinstance(ch_b, (tuple, list)) and len(ch_b) >= 4:
                cx, cy, cw, ch_h = float(ch_b[0]), float(ch_b[1]), float(ch_b[2]), float(ch_b[3])
                if any(r in ch_role for r in ("thumbnail", "anchor", "link", "title")):
                    semantic_child_pt = (cx + cw * 0.5, cy + ch_h * 0.5)
                    semantic_child_id = str(ch.get("id", f"{c_id}_child"))
                elif any(r in ch_role for r in ("badge", "button", "menu", "3dot", "more", "duration", "avatar")):
                    excluded.append(UIBoundingBox(cx, cy, cw, ch_h))

    # Safe region for video cards is the thumbnail zone (top ~65% of card) with 5% safety insets
    thumb_h = bh * 0.65 if bh > 0 else 180.0
    margin_x = bw * 0.05
    margin_y = thumb_h * 0.05
    safe_bbox = UIBoundingBox(margin_x, margin_y, max(10.0, bw - 2 * margin_x), max(10.0, thumb_h - 2 * margin_y))

    if semantic_child_pt:
        pref_pt = UIPoint(semantic_child_pt[0], semantic_child_pt[1])
        reason = "semantic_clickable_child"
    else:
        pref_pt = UIPoint(bw * 0.5, thumb_h * 0.5)
        reason = "thumbnail_safe_region"

    return SafeClickRegion(
        component_id=c_id,
        component_bbox=comp_bbox,
        safe_bbox=safe_bbox,
        preferred_point=pref_pt,
        excluded_regions=excluded,
        reason=reason,
    )


def resolve_safe_click_point(
    component_or_bbox: Any,
    component_type: str = "youtube_video",
) -> tuple[tuple[float, float], str, str]:
    """
    Semantic Safe Click Point Resolver:
    Computes a safe interaction point (local_x, local_y) within the component.
    Prioritizes:
      1. Semantic clickable child (thumbnail anchor, title link, video container)
      2. Known video thumbnail region (top ~65% of card)
      3. Clickable region of card
      4. Card safe interior
    Returns: ((local_x, local_y), target_element_id, reason)
    """
    safe_reg = build_safe_click_region(component_or_bbox, component_type=component_type)
    pref_pt = safe_reg.preferred_point

    if safe_reg.reason == "semantic_clickable_child":
        if isinstance(component_or_bbox, dict):
            for ch in component_or_bbox.get("children", []):
                if isinstance(ch, dict):
                    ch_role = (ch.get("role") or ch.get("type") or "").lower()
                    if any(r in ch_role for r in ("thumbnail", "anchor", "link", "title")):
                        return ((pref_pt.x, pref_pt.y), str(ch.get("id", f"{safe_reg.component_id}_child")), "semantic_clickable_child")
        return ((pref_pt.x, pref_pt.y), f"{safe_reg.component_id}_child", "semantic_clickable_child")

    c_id = safe_reg.component_id
    target_id = f"{c_id}_thumbnail" if c_id != "comp" else "thumbnail"
    return ((pref_pt.x, pref_pt.y), target_id, safe_reg.reason)


def resolve_clickable_region(
    component_or_bbox: Any,
    component_type: str = "youtube_video",
) -> tuple[tuple[float, float], tuple[float, float, float, float] | None, str | None]:
    """
    Semantic Clickable Region Resolver (Backward Compatibility):
    Returns: ((click_x, click_y), clickable_region_bbox, child_id)
    """
    safe_pt, child_id, reason = resolve_safe_click_point(component_or_bbox, component_type=component_type)
    if isinstance(component_or_bbox, dict):
        bbox_raw = component_or_bbox.get("bbox")
        if isinstance(bbox_raw, (tuple, list)) and len(bbox_raw) >= 4:
            w, h = float(bbox_raw[2]), float(bbox_raw[3])
        else:
            w, h = 442.0, 336.0
    elif isinstance(component_or_bbox, (tuple, list)) and len(component_or_bbox) >= 4:
        w, h = float(component_or_bbox[2]), float(component_or_bbox[3])
    else:
        w, h = 442.0, 336.0

    thumb_h = h * 0.65 if h > 0 else 180.0
    return (safe_pt, (0.0, 0.0, w, thumb_h), child_id)


def derive_safe_interaction_point(
    width_or_bbox: float | tuple[float, float, float, float] | list[float],
    height_or_type: float | str = 0.0,
    component_type: str = "youtube_video",
) -> tuple[float, float]:
    """
    Calculate a safe interaction point (x, y) relative to component top-left.
    Target the thumbnail center (top ~65% of card height), avoiding bottom badges,
    channel title, avatars, and 3-dots popup menus.
    """
    safe_pt, _, _ = resolve_safe_click_point(width_or_bbox, component_type=component_type if isinstance(height_or_type, (int, float)) else str(height_or_type))
    return safe_pt


def sort_row_major(
    components: Sequence[Any],
    y_tolerance_ratio: float = 0.25,
    default_component_type: str = "youtube_video",
    window_hwnd: int = 0,
    viewport_width: Optional[float] = None,
    viewport_height: Optional[float] = None,
    max_columns: Optional[int] = None,
) -> list[ComponentTarget]:
    """
    Determine human-like row-major visual ordering (Top -> Bottom, Left -> Right).
    Sorts components by geometric layout using adaptive vertical clustering and viewport visibility culling.

    Responsive 4-column grid:
    Row 1: #1  #2  #3  #4
    Row 2: #5  #6  #7  #8
    Row 3: #9  #10 #11 #12

    Responsive 3-column grid:
    Row 1: #1  #2  #3
    Row 2: #4  #5  #6
    Row 3: #7  #8  #9
    Row 4: #10 #11 #12

    Does NOT depend on arbitrary detector output order.
    Filters out invalid, zero-size, occluded, offscreen, or low-confidence components.
    """
    if not components:
        return []

    # 1. Resolve viewport bounds if not explicitly provided
    vp_w = viewport_width
    vp_h = viewport_height
    if vp_w is None and window_hwnd > 0:
        try:
            from .window_manager import WindowManager
            snap = WindowManager.get_snapshot(window_hwnd)
            if snap and snap.viewport_size and snap.viewport_size[0] > 0:
                vp_w = float(snap.viewport_size[0])
                vp_h = float(snap.viewport_size[1])
        except Exception:
            pass

    # 2. Normalize input components and filter candidates
    normalized_items = []
    for c in components:
        if isinstance(c, dict):
            c_id = c.get("id") or c.get("component_id") or f"comp_{len(normalized_items)+1}"
            c_type = c.get("type") or c.get("component_type") or default_component_type
            b = c.get("bbox")
            if isinstance(b, (tuple, list)) and len(b) >= 4:
                bx, by, bw, bh = float(b[0]), float(b[1]), float(b[2]), float(b[3])
            else:
                bx, by, bw, bh = 0.0, 0.0, 100.0, 100.0
            conf = float(c.get("confidence", 1.0))
            src = str(c.get("source", "CV"))
            txt = str(c.get("text", ""))
            is_visible = bool(c.get("visible", c.get("is_visible", True)))
        else:
            c_id = getattr(c, "id", getattr(c, "component_id", f"comp_{len(normalized_items)+1}"))
            c_type = getattr(c, "type", getattr(c, "component_type", default_component_type))
            if hasattr(c_type, "value"):
                c_type = c_type.value

            if hasattr(c, "bbox"):
                b = c.bbox
                if hasattr(b, "x") and hasattr(b, "y") and hasattr(b, "width") and hasattr(b, "height"):
                    bx, by, bw, bh = float(b.x), float(b.y), float(b.width), float(b.height)
                elif isinstance(b, (tuple, list)) and len(b) >= 4:
                    bx, by, bw, bh = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                else:
                    bx, by, bw, bh = 0.0, 0.0, 100.0, 100.0
            elif hasattr(c, "left") and hasattr(c, "top") and hasattr(c, "width") and hasattr(c, "height"):
                bx, by, bw, bh = float(c.left), float(c.top), float(c.width), float(c.height)
            else:
                bx, by, bw, bh = 0.0, 0.0, 100.0, 100.0
            conf = float(getattr(c, "confidence", 1.0))
            src = str(getattr(c, "source", "CV"))
            if hasattr(src, "value"):
                src = src.value
            txt = str(getattr(c, "text", ""))
            is_visible = bool(getattr(c, "visible", getattr(c, "is_visible", True)))

        # Candidate Filtering: Filter invisible, zero-size, off-viewport, low confidence
        if not is_visible:
            continue
        if bw < 20.0 or bh < 20.0:
            continue
        if bx < -100.0 or by < -100.0:
            continue
        if conf < 0.2:
            continue

        # Visibility Culling against viewport width & height
        if vp_w and vp_w > 0:
            if bx >= vp_w or (bx + bw * 0.5) > vp_w:
                log.debug("[ROW_MAJOR_SORT] Culled offscreen element %s (x=%.1f >= viewport_w=%.1f)", c_id, bx, vp_w)
                continue
        if vp_h and vp_h > 0:
            if by >= vp_h or (by + bh * 0.5) > vp_h:
                log.debug("[ROW_MAJOR_SORT] Culled offscreen element %s (y=%.1f >= viewport_h=%.1f)", c_id, by, vp_h)
                continue

        cx = bx + bw / 2.0
        cy = by + bh / 2.0

        normalized_items.append({
            "id": str(c_id),
            "type": str(c_type),
            "bbox": (bx, by, bw, bh),
            "center": (cx, cy),
            "confidence": conf,
            "source": src,
            "text": txt,
        })

    if not normalized_items:
        return []

    # 3. Compute adaptive Y-tolerance from median component height
    heights = sorted([item["bbox"][3] for item in normalized_items if item["bbox"][3] > 0])
    median_h = heights[len(heights) // 2] if heights else 100.0
    y_tolerance = max(15.0, median_h * y_tolerance_ratio)

    # Sort initially by top Y to process downwards
    sorted_by_y = sorted(normalized_items, key=lambda it: (it["bbox"][1], it["bbox"][0]))

    rows: list[list[dict[str, Any]]] = []
    row_centers_y: list[float] = []

    # 4. Adaptive row clustering (handles slight vertical displacements across cards)
    for item in sorted_by_y:
        c_y = item["center"][1]
        matched_row_idx = -1
        min_dist = float("inf")

        for r_idx, r_center in enumerate(row_centers_y):
            dist = abs(c_y - r_center)
            if dist < y_tolerance and dist < min_dist:
                min_dist = dist
                matched_row_idx = r_idx

        if matched_row_idx >= 0:
            rows[matched_row_idx].append(item)
            row_items = rows[matched_row_idx]
            row_centers_y[matched_row_idx] = sum(it["center"][1] for it in row_items) / len(row_items)
        else:
            rows.append([item])
            row_centers_y.append(c_y)

    # 5. Sort each row Left -> Right
    for row in rows:
        row.sort(key=lambda it: it["center"][0])

    # 6. Sort rows Top -> Bottom
    combined = list(zip(rows, row_centers_y))
    combined.sort(key=lambda pair: pair[1])
    sorted_rows = [pair[0] for pair in combined]

    # 7. Assign 1-based ordinals in row-major sequence
    ordered_targets: list[ComponentTarget] = []
    ordinal_counter = 1

    for r_idx, row in enumerate(sorted_rows):
        for c_idx, item in enumerate(row):
            bx, by, bw, bh = item["bbox"]
            safe_pt, _, _ = resolve_safe_click_point(item, component_type=item["type"])

            target = ComponentTarget(
                component_id=item["id"],
                component_type=item["type"],
                bbox=(bx, by, bw, bh),
                center=item["center"],
                safe_click_point=safe_pt,
                ordinal=ordinal_counter,
                row=r_idx,
                column=c_idx,
                confidence=item["confidence"],
                source=item["source"],
                text=item["text"],
                window_hwnd=window_hwnd,
            )
            ordered_targets.append(target)
            ordinal_counter += 1

    log.info(
        "[ROW_MAJOR_SORT] Ordered %d components into %d rows (y_tolerance=%.1fpx)",
        len(ordered_targets), len(sorted_rows), y_tolerance
    )

    return ordered_targets

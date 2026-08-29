"""
Data models and type definitions for Hermes UI Perception and Targeting Subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Optional


class RegionType(str, Enum):
    SCREEN = "SCREEN"
    WINDOW = "WINDOW"
    BROWSER_CHROME = "BROWSER_CHROME"
    WEBPAGE = "WEBPAGE"
    HEADER = "HEADER"
    SIDEBAR = "SIDEBAR"
    MAIN_CONTENT = "MAIN_CONTENT"
    FOOTER = "FOOTER"
    RIGHT_PANEL = "RIGHT_PANEL"
    LEFT_PANEL = "LEFT_PANEL"
    MODAL = "MODAL"
    DIALOG = "DIALOG"
    OVERLAY = "OVERLAY"
    FLOATING_PANEL = "FLOATING_PANEL"
    ACTIVE_PANEL = "ACTIVE_PANEL"


class LayoutType(str, Enum):
    GRID = "GRID"
    LIST = "LIST"
    HORIZONTAL_LIST = "HORIZONTAL_LIST"
    VERTICAL_LIST = "VERTICAL_LIST"
    SIDEBAR = "SIDEBAR"
    NAVBAR = "NAVBAR"
    TOOLBAR = "TOOLBAR"
    CAROUSEL = "CAROUSEL"
    TABLE = "TABLE"
    FORM = "FORM"
    PANEL = "PANEL"
    MODAL = "MODAL"
    OVERLAY = "OVERLAY"
    CARD_CONTAINER = "CARD_CONTAINER"
    UNKNOWN = "UNKNOWN"


class ElementType(str, Enum):
    BUTTON = "BUTTON"
    LINK = "LINK"
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    ICON = "ICON"
    INPUT = "INPUT"
    SEARCH_INPUT = "SEARCH_INPUT"
    SEARCH_BUTTON = "SEARCH_BUTTON"
    CHECKBOX = "CHECKBOX"
    RADIO = "RADIO"
    SELECT = "SELECT"
    TAB = "TAB"
    NAV_ITEM = "NAV_ITEM"

    # Media & Content
    VIDEO = "VIDEO"
    VIDEO_CARD = "VIDEO_CARD"
    SHORT_CARD = "SHORT_CARD"
    PLAYLIST = "PLAYLIST"
    PLAYLIST_CARD = "PLAYLIST_CARD"
    PLAYLIST_ITEM = "PLAYLIST_ITEM"
    THUMBNAIL = "THUMBNAIL"
    DURATION_BADGE = "DURATION_BADGE"
    TITLE = "TITLE"
    CHANNEL = "CHANNEL"
    METADATA = "METADATA"
    MORE_BUTTON = "MORE_BUTTON"
    CLOSE_BUTTON = "CLOSE_BUTTON"

    # Structure & Navigation
    SIDEBAR = "SIDEBAR"
    SIDEBAR_ITEM = "SIDEBAR_ITEM"
    NAVBAR = "NAVBAR"
    TOOLBAR = "TOOLBAR"
    MODAL = "MODAL"
    DIALOG = "DIALOG"
    OVERLAY = "OVERLAY"
    ADVERTISEMENT = "ADVERTISEMENT"
    PROMOTED = "PROMOTED"
    SPONSORED = "SPONSORED"

    # Tables & Grid
    TABLE = "TABLE"
    TABLE_ROW = "TABLE_ROW"
    TABLE_CELL = "TABLE_CELL"
    UNKNOWN = "UNKNOWN"


class VisibilityState(str, Enum):
    VISIBLE = "VISIBLE"
    PARTIALLY_VISIBLE = "PARTIALLY_VISIBLE"
    OCCLUDED = "OCCLUDED"
    OFFSCREEN = "OFFSCREEN"
    HIDDEN = "HIDDEN"


class SpatialRelation(str, Enum):
    LEFT_OF = "LEFT_OF"
    RIGHT_OF = "RIGHT_OF"
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    INSIDE = "INSIDE"
    CONTAINS = "CONTAINS"
    NEAR = "NEAR"
    OVERLAPS = "OVERLAPS"
    ADJACENT_TO = "ADJACENT_TO"


class UIState(str, Enum):
    NORMAL = "NORMAL"
    HOVER = "HOVER"
    FOCUSED = "FOCUSED"
    SELECTED = "SELECTED"
    PRESSED = "PRESSED"
    EXPANDED = "EXPANDED"
    COLLAPSED = "COLLAPSED"
    LOADING = "LOADING"
    DISABLED = "DISABLED"


class ResolutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_OFFSCREEN = "TARGET_OFFSCREEN"
    TARGET_OCCLUDED = "TARGET_OCCLUDED"
    TARGET_NOT_INTERACTIVE = "TARGET_NOT_INTERACTIVE"
    CONTAINER_NOT_FOUND = "CONTAINER_NOT_FOUND"
    LAYOUT_UNCERTAIN = "LAYOUT_UNCERTAIN"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UI_UNSTABLE = "UI_UNSTABLE"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class ActionType(str, Enum):
    CLICK = "CLICK"
    OPEN = "OPEN"
    OPEN_MENU = "OPEN_MENU"
    FOCUS = "FOCUS"
    HOVER = "HOVER"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    SCROLL = "SCROLL"
    PLAY = "PLAY"


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class BoundingBox:
    """
    Normalized or pixel bounding box (x, y, width, height).
    x, y represent the top-left corner.
    """
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def center(self) -> Point:
        return Point(self.center_x, self.center_y)

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def contains_point(self, p: Point) -> bool:
        return self.left <= p.x <= self.right and self.top <= p.y <= self.bottom

    def contains_bbox(self, other: BoundingBox, margin: float = 0.0) -> bool:
        return (
            (self.left - margin) <= other.left
            and (self.right + margin) >= other.right
            and (self.top - margin) <= other.top
            and (self.bottom + margin) >= other.bottom
        )

    def overlaps(self, other: BoundingBox) -> bool:
        return not (
            self.right <= other.left
            or self.left >= other.right
            or self.bottom <= other.top
            or self.top >= other.bottom
        )

    def intersection(self, other: BoundingBox) -> Optional[BoundingBox]:
        ix1 = max(self.left, other.left)
        iy1 = max(self.top, other.top)
        ix2 = min(self.right, other.right)
        iy2 = min(self.bottom, other.bottom)
        if ix2 > ix1 and iy2 > iy1:
            return BoundingBox(x=ix1, y=iy1, width=ix2 - ix1, height=iy2 - iy1)
        return None

    def iou(self, other: BoundingBox) -> float:
        inter = self.intersection(other)
        if not inter:
            return 0.0
        inter_area = inter.area
        union_area = self.area + other.area - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "width": round(self.width, 4),
            "height": round(self.height, 4),
            "center_x": round(self.center_x, 4),
            "center_y": round(self.center_y, 4),
        }


@dataclass
class UIElement:
    """
    Comprehensive representation of a UI element or component in the Semantic Tree.
    """
    id: str
    type: ElementType
    semantic_role: str = ""
    bbox: BoundingBox = field(default_factory=lambda: BoundingBox(0, 0, 0, 0))

    # Hierarchy and Containment IDs
    parent_id: Optional[str] = None
    container_id: Optional[str] = None
    region_id: Optional[str] = None
    section_id: Optional[str] = None
    scope: str = "WEBPAGE"  # "BROWSER_CHROME" | "WEBPAGE" | "OVERLAY"

    # Spatial & Semantic Ordering
    row: int = -1
    column: int = -1
    index: int = -1
    visual_index: int = -1
    reading_index: int = -1
    interaction_index: int = -1

    # Content & Text
    text: str = ""
    normalized_text: str = ""

    # Visibility & Occlusion
    visibility: VisibilityState = VisibilityState.VISIBLE
    is_occluded: bool = False
    occluded_by: Optional[str] = None
    z_order: int = 0

    # Interaction Capabilities
    interactive: bool = True
    clickable: bool = True
    hoverable: bool = False
    focusable: bool = False
    editable: bool = False
    scrollable: bool = False
    draggable: bool = False
    expandable: bool = False

    # State & Quality
    state: UIState = UIState.NORMAL
    confidence: float = 1.0
    stability: float = 1.0
    is_advertisement: bool = False

    # Tree links
    children: list[UIElement] = field(default_factory=list)
    interaction_targets: dict[str, BoundingBox] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "semantic_role": self.semantic_role,
            "bbox": self.bbox.to_dict(),
            "scope": self.scope,
            "region_id": self.region_id,
            "container_id": self.container_id,
            "section_id": self.section_id,
            "row": self.row,
            "column": self.column,
            "visual_index": self.visual_index,
            "text": self.text,
            "visibility": self.visibility.value,
            "interactive": self.interactive,
            "is_ad": self.is_advertisement,
            "children_count": len(self.children),
        }


@dataclass
class UIRegion:
    """A major structural screen or webpage region."""
    id: str
    type: RegionType
    bbox: BoundingBox
    scope: str = "WEBPAGE"  # "BROWSER_CHROME" | "WEBPAGE" | "OVERLAY"
    parent_id: Optional[str] = None
    z_order: int = 0
    visibility: VisibilityState = VisibilityState.VISIBLE
    confidence: float = 1.0
    is_blocking: bool = False
    scroll_context: Optional[str] = None
    containers: list[str] = field(default_factory=list)
    element_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "scope": self.scope,
            "bbox": self.bbox.to_dict(),
            "z_order": self.z_order,
            "is_blocking": self.is_blocking,
            "containers_count": len(self.containers),
            "elements_count": len(self.element_ids),
        }


@dataclass
class UIContainer:
    """A layout container grouping elements (e.g. Video Grid, Shorts List, Sidebar Menu)."""
    id: str
    region_id: str
    layout_type: LayoutType
    bbox: BoundingBox
    name: str = ""
    section_name: str = ""
    rows_count: int = 0
    columns_count: int = 0
    scrollable: bool = False
    scroll_type: str = "NONE"  # "PAGE_SCROLL", "SIDEBAR_SCROLL", "PLAYLIST_SCROLL", etc.
    element_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "region_id": self.region_id,
            "name": self.name,
            "section_name": self.section_name,
            "layout_type": self.layout_type.value,
            "rows": self.rows_count,
            "columns": self.columns_count,
            "scrollable": self.scrollable,
            "elements_count": len(self.element_ids),
        }


@dataclass
class CompositeComponent:
    """A compound UI object consisting of multiple linked elements."""
    id: str
    type: ElementType
    container_id: str
    bbox: BoundingBox
    visual_index: int = -1
    row: int = -1
    column: int = -1
    is_advertisement: bool = False

    # Sub-parts mapping
    thumbnail: Optional[UIElement] = None
    title: Optional[UIElement] = None
    channel: Optional[UIElement] = None
    duration: Optional[UIElement] = None
    metadata: Optional[UIElement] = None
    more_button: Optional[UIElement] = None
    header: Optional[UIElement] = None
    items: list[UIElement] = field(default_factory=list)
    raw_element: Optional[UIElement] = None

    def get_preferred_click_target(self, action: ActionType = ActionType.OPEN) -> Optional[UIElement]:
        """Resolve the safe interaction sub-target for a given action."""
        if action == ActionType.OPEN_MENU:
            return self.more_button or self.raw_element
        elif action in (ActionType.OPEN, ActionType.PLAY, ActionType.CLICK):
            return self.thumbnail or self.title or self.raw_element
        elif action == ActionType.FOCUS:
            return self.title or self.raw_element
        return self.raw_element


@dataclass
class UITree:
    """The root hierarchical Semantic Tree of the perceivable screen/window."""
    screen_width: int
    screen_height: int
    window_title: str = ""
    app_name: str = ""
    is_browser: bool = False
    timestamp: float = 0.0
    stability_score: float = 1.0

    regions: dict[str, UIRegion] = field(default_factory=dict)
    containers: dict[str, UIContainer] = field(default_factory=dict)
    elements: dict[str, UIElement] = field(default_factory=dict)
    composites: dict[str, CompositeComponent] = field(default_factory=dict)

    # Ordered indices
    reading_order: list[str] = field(default_factory=list)
    interaction_order: list[str] = field(default_factory=list)
    visual_groups: dict[str, list[str]] = field(default_factory=dict)

    def get_element(self, elem_id: str) -> Optional[UIElement]:
        return self.elements.get(elem_id)

    def get_container(self, cont_id: str) -> Optional[UIContainer]:
        return self.containers.get(cont_id)

    def get_region(self, reg_id: str) -> Optional[UIRegion]:
        return self.regions.get(reg_id)

    def get_composite(self, comp_id: str) -> Optional[CompositeComponent]:
        return self.composites.get(comp_id)

    def find_blocking_overlay(self) -> Optional[UIRegion]:
        """Find any modal or dialog that is currently blocking user interactions."""
        for reg in self.regions.values():
            if reg.is_blocking and reg.visibility == VisibilityState.VISIBLE:
                return reg
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_title": self.window_title,
            "app_name": self.app_name,
            "screen_size": (self.screen_width, self.screen_height),
            "stability_score": round(self.stability_score, 3),
            "regions_count": len(self.regions),
            "containers_count": len(self.containers),
            "elements_count": len(self.elements),
            "composites_count": len(self.composites),
        }


@dataclass
class TargetQuery:
    """Structured query specifying what the user wants to select or click."""
    raw_query: str
    semantic_type: Optional[ElementType] = None
    child_type: Optional[ElementType] = None  # e.g. MORE_BUTTON, THUMBNAIL, TITLE
    action_type: ActionType = ActionType.OPEN

    # Ordinals and Coordinates
    ordinal_index: Optional[int] = None  # 1-based or 0-based index
    row: Optional[int] = None
    column: Optional[int] = None

    # Text and Substrings
    text_pattern: Optional[str] = None
    exact_text: Optional[str] = None

    # Scope & Container filters
    region_type: Optional[RegionType] = None
    section_name: Optional[str] = None  # e.g. "Shorts", "Playlist", "Sidebar"
    container_id: Optional[str] = None

    # Spatial Relation
    spatial_relation: Optional[SpatialRelation] = None
    anchor_query: Optional[str] = None
    anchor_element_id: Optional[str] = None


@dataclass
class CandidateMatch:
    """A scored target candidate."""
    element: UIElement
    composite: Optional[CompositeComponent] = None
    total_score: float = 0.0
    semantic_score: float = 0.0
    text_score: float = 0.0
    container_score: float = 0.0
    ordinal_score: float = 0.0
    spatial_score: float = 0.0
    match_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class InteractionPoint:
    """Precise coordinates and safety attributes for physical click/interaction."""
    pixel_x: int
    pixel_y: int
    normalized_x: float
    normalized_y: float
    target_element_id: str
    target_type: ElementType
    action_type: ActionType
    is_safe: bool = True
    safety_margin: float = 0.1
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pixel": (self.pixel_x, self.pixel_y),
            "normalized": (round(self.normalized_x, 4), round(self.normalized_y, 4)),
            "element_id": self.target_element_id,
            "target_type": self.target_type.value,
            "action": self.action_type.value,
            "is_safe": self.is_safe,
            "reason": self.reason,
        }


@dataclass
class ResolutionResult:
    """Result returned by TargetResolver."""
    status: ResolutionStatus
    query: TargetQuery
    target_element: Optional[UIElement] = None
    composite: Optional[CompositeComponent] = None
    interaction_point: Optional[InteractionPoint] = None
    confidence: float = 0.0
    candidates_count: int = 0
    top_candidates: list[CandidateMatch] = field(default_factory=list)
    error_message: str = ""
    suggested_action: Optional[str] = None  # e.g. "SCROLL_CONTAINER:playlist"

    def is_success(self) -> bool:
        return self.status == ResolutionStatus.SUCCESS and self.interaction_point is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence": round(self.confidence, 3),
            "target_id": self.target_element.id if self.target_element else None,
            "interaction_point": self.interaction_point.to_dict() if self.interaction_point else None,
            "error_message": self.error_message,
            "suggested_action": self.suggested_action,
        }


@dataclass
class VerificationResult:
    """Result of verifying interaction success."""
    success: bool
    status: ResolutionStatus
    state_change_detected: bool = False
    expected_state: str = ""
    actual_state: str = ""
    confidence: float = 1.0
    message: str = ""
    needs_re_localization: bool = False

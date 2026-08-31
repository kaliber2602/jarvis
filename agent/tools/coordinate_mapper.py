"""
Single Source of Truth Coordinate Transformation Engine.
Provides explicit, deterministic coordinate mappings across:
  COMPONENT_SPACE -> VIEWPORT_SPACE -> WINDOW_CLIENT_SPACE -> SCREEN_SPACE
Strictly avoids duplicate offsets, assumed coordinates, or double DPI scaling.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any, Optional

log = logging.getLogger("hermes.coordinate_mapper")


class CoordinateSpace(str, Enum):
    """Explicit coordinate spaces with precise semantics."""
    COMPONENT_SPACE = "COMPONENT_SPACE"          # Local to a component (top-left is 0, 0)
    VIEWPORT_SPACE = "VIEWPORT_SPACE"            # Document / webpage viewport (webpage top-left is 0, 0)
    WINDOW_CLIENT_SPACE = "WINDOW_CLIENT_SPACE"  # Window client area (top-left is 0, 0, includes browser chrome toolbar)
    SCREEN_SPACE = "SCREEN_SPACE"                # Physical screen coordinates in Windows monitor desktop pixels


@dataclass(frozen=True)
class Point:
    """2D Point tagged with coordinate space."""
    x: float
    y: float
    space: CoordinateSpace = CoordinateSpace.SCREEN_SPACE

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    def to_int_tuple(self) -> tuple[int, int]:
        return (int(round(self.x)), int(round(self.y)))


@dataclass(frozen=True)
class BoundingBox:
    """2D Bounding Box in a specific coordinate space."""
    x: float
    y: float
    width: float
    height: float
    space: CoordinateSpace = CoordinateSpace.VIEWPORT_SPACE

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

    def contains(self, point_x: float, point_y: float) -> bool:
        """Check if a point is contained within this bounding box."""
        return (self.left <= point_x <= self.right and self.top <= point_y <= self.bottom)

    def to_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)


class CoordinateMapper:
    """
    Unified Coordinate Transformation Service.
    Single source of truth for converting UI perception and component coordinates to physical screen coordinates.
    """

    @classmethod
    def component_to_viewport(
        cls,
        comp_point: tuple[float, float],
        comp_bbox: tuple[float, float, float, float] | BoundingBox,
    ) -> tuple[float, float]:
        """
        Step 1: Convert component-local coordinates (relative to component top-left)
        to viewport coordinates (relative to webpage document top-left).
        """
        if isinstance(comp_bbox, BoundingBox):
            bx, by = comp_bbox.x, comp_bbox.y
        else:
            bx, by = comp_bbox[0], comp_bbox[1]

        vx = bx + comp_point[0]
        vy = by + comp_point[1]
        return (vx, vy)

    @classmethod
    def viewport_to_client(
        cls,
        viewport_point: tuple[float, float],
        browser_chrome_height: int = 0,
    ) -> tuple[float, float]:
        """
        Step 2: Convert viewport coordinates to window client area coordinates.
        In browser windows, the document viewport sits directly below the browser top toolbar
        (tabs + omnibox = browser_chrome_height).
        """
        cx = viewport_point[0]
        cy = viewport_point[1] + browser_chrome_height
        return (cx, cy)

    @classmethod
    def client_to_screen(
        cls,
        client_point: tuple[float, float],
        client_screen_origin: tuple[int, int],
    ) -> tuple[int, int]:
        """
        Step 3: Convert window client area coordinates to physical desktop screen coordinates.
        Uses the Win32 ClientToScreen origin of the client area.
        """
        sx = client_screen_origin[0] + client_point[0]
        sy = client_screen_origin[1] + client_point[1]
        return (int(round(sx)), int(round(sy)))

    @classmethod
    def to_screen(
        cls,
        comp_point: tuple[float, float],
        comp_bbox: tuple[float, float, float, float] | BoundingBox,
        client_screen_origin: tuple[int, int],
        browser_chrome_height: int = 0,
        window_geometry: Optional[Any] = None,
        dpi_scale: float = 1.0,
    ) -> tuple[tuple[int, int], dict[str, Any]]:
        """
        Full 4-tier transformation pipeline with diagnostic trace and containment verification:
          COMPONENT -> VIEWPORT -> CLIENT -> SCREEN
        """
        # Step 1: Component -> Viewport
        vp_x, vp_y = cls.component_to_viewport(comp_point, comp_bbox)

        # Step 2: Viewport -> Client
        cl_x, cl_y = cls.viewport_to_client((vp_x, vp_y), browser_chrome_height=browser_chrome_height)

        # Step 3: Client -> Screen
        sc_x, sc_y = cls.client_to_screen((cl_x, cl_y), client_screen_origin=client_screen_origin)
        if dpi_scale and dpi_scale != 1.0:
            sc_x = int(round(sc_x * dpi_scale))
            sc_y = int(round(sc_y * dpi_scale))

        # Validation: Verify viewport point is inside component bbox
        if isinstance(comp_bbox, BoundingBox):
            bbox_obj = comp_bbox
        else:
            bbox_obj = BoundingBox(x=comp_bbox[0], y=comp_bbox[1], width=comp_bbox[2], height=comp_bbox[3])

        is_inside = bbox_obj.contains(vp_x, vp_y)

        trace = {
            "component_space": (round(comp_point[0], 2), round(comp_point[1], 2)),
            "viewport_space": (round(vp_x, 2), round(vp_y, 2)),
            "window_client_space": (round(cl_x, 2), round(cl_y, 2)),
            "screen_space": (sc_x, sc_y),
            "browser_chrome_height": browser_chrome_height,
            "client_screen_origin": client_screen_origin,
            "bbox": bbox_obj.to_tuple(),
            "is_inside_bbox": is_inside,
            "success": True,
            "error": None if is_inside else "Target point outside component bounding box",
        }

        log.info(
            "\n[SAFE_POINT]\n"
            "bbox:\n"
            "  x=%.1f\n"
            "  y=%.1f\n"
            "  width=%.1f\n"
            "  height=%.1f\n"
            "local_point=(%.1f, %.1f)\n"
            "absolute_component_point=(%.1f, %.1f)\n"
            "inside_bbox=%s\n\n"
            "[COORD_TRANSFORM] Step 1:\n"
            "  input_space=COMPONENT_LOCAL_SPACE input=(%.1f, %.1f)\n"
            "  output_space=VIEWPORT_SPACE output=(%.1f, %.1f)\n"
            "  transform=vx = bbox_x + lx (%.1f + %.1f), vy = bbox_y + ly (%.1f + %.1f)\n\n"
            "[COORD_TRANSFORM] Step 2:\n"
            "  input_space=VIEWPORT_SPACE input=(%.1f, %.1f)\n"
            "  output_space=WINDOW_CLIENT_SPACE output=(%.1f, %.1f)\n"
            "  transform=cx = vx, cy = vy + chrome_h (%.1f + %d)\n\n"
            "[COORD_TRANSFORM] Step 3:\n"
            "  input_space=WINDOW_CLIENT_SPACE input=(%.1f, %.1f)\n"
            "  output_space=PHYSICAL_SCREEN_SPACE output=(%d, %d)\n"
            "  transform=sx = origin_x + cx (%d + %.1f), sy = origin_y + cy (%d + %.1f)",
            bbox_obj.x, bbox_obj.y, bbox_obj.width, bbox_obj.height,
            round(comp_point[0], 1), round(comp_point[1], 1),
            round(vp_x, 1), round(vp_y, 1),
            is_inside,
            round(comp_point[0], 1), round(comp_point[1], 1),
            round(vp_x, 1), round(vp_y, 1),
            bbox_obj.x, round(comp_point[0], 1), bbox_obj.y, round(comp_point[1], 1),
            round(vp_x, 1), round(vp_y, 1),
            round(cl_x, 1), round(cl_y, 1),
            round(vp_y, 1), browser_chrome_height,
            round(cl_x, 1), round(cl_y, 1),
            sc_x, sc_y,
            client_screen_origin[0], round(cl_x, 1), client_screen_origin[1], round(cl_y, 1),
        )

        log.info(
            "[COORDINATE_MAPPER]\n"
            "  component_space: (%s, %s)\n"
            "  viewport_space:  (%s, %s)\n"
            "  client_space:    (%s, %s)\n"
            "  screen_space:    (%d, %d)\n"
            "  inside_bbox:     %s",
            round(comp_point[0], 1), round(comp_point[1], 1),
            round(vp_x, 1), round(vp_y, 1),
            round(cl_x, 1), round(cl_y, 1),
            sc_x, sc_y,
            is_inside,
        )

        return (sc_x, sc_y), trace

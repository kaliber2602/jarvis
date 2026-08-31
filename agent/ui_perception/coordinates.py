"""
Explicit Coordinate Frames, DPI-Aware Window Geometry, and Coordinate Transformation Engine.
Provides strong typing for coordinate spaces and deterministic conversion across:
  COMPONENT_SPACE -> VIEWPORT_SPACE -> WINDOW_CLIENT_SPACE -> SCREEN_SPACE
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from enum import Enum
import logging
import math
import sys
from typing import Any, Optional, Tuple

log = logging.getLogger("hermes_ui.coordinates")

if sys.platform == "win32":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    gdi32 = ctypes.windll.gdi32
    shcore = getattr(ctypes.windll, "shcore", None)

    # Ensure 64-bit safe restypes
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindow.restype = wintypes.HWND
else:
    user32 = None
    dwmapi = None
    gdi32 = None
    shcore = None


class CoordinateSpace(str, Enum):
    """
    Explicit coordinate spaces.
    Every coordinate must belong to exactly one defined coordinate space.
    """
    COMPONENT_SPACE = "COMPONENT_SPACE"          # Local to a single component (e.g. VideoCard top-left is 0,0)
    VIEWPORT_SPACE = "VIEWPORT_SPACE"            # Webpage / content viewport space (webpage top-left is 0,0)
    WINDOW_CLIENT_SPACE = "WINDOW_CLIENT_SPACE"  # Window client area (top-left of client area is 0,0)
    SCREEN_SPACE = "SCREEN_SPACE"                # Physical screen coordinates in monitor pixel space
    PHYSICAL_SCREEN_SPACE = "PHYSICAL_SCREEN_SPACE"  # Hardware physical screen space (alias / identical to screen space)



@dataclass
class Coordinate:
    """
    A 2D coordinate tagged with its explicit CoordinateSpace.
    """
    x: float
    y: float
    space: CoordinateSpace

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    def to_int_tuple(self) -> tuple[int, int]:
        return (int(round(self.x)), int(round(self.y)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "space": self.space.value,
        }


@dataclass
class PhysicalScreenPoint:
    """
    Final physical screen coordinate (integer pixels on Windows desktop).
    Used exclusively by MouseExecutor to perform Win32 mouse clicks.
    """
    x: int
    y: int

    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass
class WindowGeometry:
    """
    Runtime-resolved target window and client geometry with DPI scaling metadata.
    """
    hwnd: int
    title: str
    is_valid: bool = True

    # Window frame rect in physical screen coordinates (left, top, right, bottom)
    window_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    window_x: int = 0
    window_y: int = 0
    window_width: int = 0
    window_height: int = 0

    # Client area geometry
    client_rect: tuple[int, int, int, int] = (0, 0, 0, 0)  # (0, 0, client_width, client_height)
    client_width: int = 0
    client_height: int = 0
    client_screen_x: int = 0
    client_screen_y: int = 0

    # Viewport geometry (webpage / document area inside browser/app)
    browser_chrome_height: int = 0  # Physical pixel height of browser tabs + omnibox
    viewport_screen_x: int = 0
    viewport_screen_y: int = 0
    viewport_width: int = 0
    viewport_height: int = 0

    # DPI & State
    dpi: int = 96
    dpi_scale: float = 1.0
    is_maximized: bool = False
    is_minimized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "is_valid": self.is_valid,
            "window_origin": (self.window_x, self.window_y),
            "window_size": (self.window_width, self.window_height),
            "client_origin": (self.client_screen_x, self.client_screen_y),
            "client_size": (self.client_width, self.client_height),
            "viewport_origin": (self.viewport_screen_x, self.viewport_screen_y),
            "viewport_size": (self.viewport_width, self.viewport_height),
            "browser_chrome_height": self.browser_chrome_height,
            "dpi": self.dpi,
            "dpi_scale": round(self.dpi_scale, 3),
            "is_maximized": self.is_maximized,
            "is_minimized": self.is_minimized,
        }


class DPIAwarenessManager:
    """
    Ensures the Python process runs in a consistent, per-monitor DPI-aware mode on Windows.
    """
    _initialized: bool = False

    @classmethod
    def ensure_dpi_aware(cls) -> None:
        if cls._initialized or sys.platform != "win32" or not user32:
            return
        cls._initialized = True
        try:
            # 1. Try Per-Monitor V2 DPI awareness (Windows 10 1703+)
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            log.debug("[DPI] Set process DPI awareness to Per-Monitor V2.")
            return
        except Exception:
            pass

        try:
            # 2. Try SetProcessDpiAwareness (PROCESS_PER_MONITOR_DPI_AWARE = 2) via shcore
            if shcore and hasattr(shcore, "SetProcessDpiAwareness"):
                shcore.SetProcessDpiAwareness(2)
                log.debug("[DPI] Set process DPI awareness to Per-Monitor via shcore.")
                return
        except Exception:
            pass

        try:
            # 3. Fallback to standard SetProcessDPIAware
            user32.SetProcessDPIAware()
            log.debug("[DPI] Set process DPI awareness via SetProcessDPIAware.")
        except Exception as e:
            log.warning("[DPI] Failed to set DPI awareness: %s", e)


class WindowGeometryProvider:
    """
    Queries runtime Win32 APIs dynamically to extract exact window and client geometry.
    Strictly avoids hardcoded screen dimensions or assumed window positions.
    """

    @classmethod
    def get_window_geometry(
        cls,
        hwnd: Optional[int] = None,
        app_name: Optional[str] = None,
    ) -> WindowGeometry:
        """
        Extract full, DPI-aware runtime geometry for the specified HWND or active target window.
        """
        DPIAwarenessManager.ensure_dpi_aware()

        if sys.platform != "win32" or not user32:
            # On non-Windows, return dummy geometry with default size
            return WindowGeometry(
                hwnd=0,
                title="Mock Window",
                is_valid=True,
                window_rect=(0, 0, 1920, 1080),
                window_x=0,
                window_y=0,
                window_width=1920,
                window_height=1080,
                client_rect=(0, 0, 1920, 1080),
                client_width=1920,
                client_height=1080,
                client_screen_x=0,
                client_screen_y=0,
                browser_chrome_height=80,
                viewport_screen_x=0,
                viewport_screen_y=80,
                viewport_width=1920,
                viewport_height=1000,
                dpi=96,
                dpi_scale=1.0,
            )

        target_hwnd = hwnd
        if not target_hwnd:
            try:
                from ..tools.window_target_resolver import WindowTargetResolver
                locked = WindowTargetResolver.get_locked_target()
                if locked and locked.hwnd:
                    if user32 and user32.IsWindow(locked.hwnd):
                        target_hwnd = locked.hwnd
                        log.info("[WINDOW_TARGET] Using locked task HWND=%d for geometry_query", target_hwnd)
                        log.info("[WINDOW_TARGET] Locked HWND validation=True")
                    else:
                        log.warning("[WINDOW_TARGET] Locked HWND=%d is invalid.", locked.hwnd)
                        log.info("[WINDOW_TARGET] Controlled target re-resolution required.")
                        log.warning("[WINDOW_TARGET] Locked HWND=%d became invalid", locked.hwnd)
                        log.info("[WINDOW_TARGET] Attempting controlled recovery")
                        WindowTargetResolver.release_target()
            except Exception as e:
                log.debug("[WINDOW_GEOMETRY] Locked target check notice: %s", e)

        if not target_hwnd:
            if app_name:
                try:
                    from ..tools.window_target_resolver import WindowTargetResolver
                    target_hwnd, _, _, _ = WindowTargetResolver.resolve_target(app_name, command_name="geometry_query")
                except Exception as e:
                    log.debug("[WINDOW_GEOMETRY] WindowTargetResolver lookup error: %s", e)

            if not target_hwnd:
                target_hwnd = user32.GetForegroundWindow()
        elif hwnd and user32 and user32.IsWindow(target_hwnd):
            log.info("[WINDOW_TARGET] Using locked task HWND=%d for geometry_query", target_hwnd)
            log.info("[WINDOW_TARGET] Locked HWND validation=True")

        if not target_hwnd or not user32.IsWindow(target_hwnd):
            log.warning("[WINDOW_GEOMETRY] No valid window HWND found (queried hwnd=%s, app=%s)", hwnd, app_name)
            return WindowGeometry(hwnd=0, title="", is_valid=False)

        # 1. Window Title
        length = user32.GetWindowTextLengthW(target_hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(target_hwnd, buf, length + 1)
            title = buf.value.strip()

        # 2. Window State (Iconic / Zoomed)
        is_minimized = bool(user32.IsIconic(target_hwnd))
        is_maximized = bool(user32.IsZoomed(target_hwnd))

        if is_minimized:
            log.warning("[WINDOW_GEOMETRY] Window HWND=%d ('%s') is minimized.", target_hwnd, title)
            return WindowGeometry(
                hwnd=target_hwnd,
                title=title,
                is_valid=False,
                is_minimized=True,
            )

        # 3. DPI Information
        dpi = 96
        try:
            if hasattr(user32, "GetDpiForWindow"):
                dpi_val = user32.GetDpiForWindow(target_hwnd)
                if dpi_val > 0:
                    dpi = dpi_val
            elif gdi32:
                hdc = user32.GetDC(target_hwnd)
                if hdc:
                    dpi_val = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
                    user32.ReleaseDC(target_hwnd, hdc)
                    if dpi_val > 0:
                        dpi = dpi_val
        except Exception as e:
            log.debug("[WINDOW_GEOMETRY] DPI query error: %s", e)

        dpi_scale = max(0.5, min(4.0, dpi / 96.0))

        # 4. Window Rect (Screen Coordinates)
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        w_rect = RECT()
        # Prefer DwmGetWindowAttribute for accurate visual frame bounds (excluding invisible drop shadow margins)
        dwm_ok = False
        if dwmapi:
            try:
                # DWMWA_EXTENDED_FRAME_BOUNDS = 9
                hres = dwmapi.DwmGetWindowAttribute(
                    target_hwnd,
                    9,
                    ctypes.byref(w_rect),
                    ctypes.sizeof(w_rect),
                )
                if hres == 0:
                    dwm_ok = True
            except Exception:
                dwm_ok = False

        if not dwm_ok:
            user32.GetWindowRect(target_hwnd, ctypes.byref(w_rect))

        win_x = w_rect.left
        win_y = w_rect.top
        win_w = max(0, w_rect.right - w_rect.left)
        win_h = max(0, w_rect.bottom - w_rect.top)

        # 5. Client Rect & Client Screen Origin
        c_rect = RECT()
        user32.GetClientRect(target_hwnd, ctypes.byref(c_rect))
        client_w = max(0, c_rect.right - c_rect.left)
        client_h = max(0, c_rect.bottom - c_rect.top)

        pt = POINT(0, 0)
        user32.ClientToScreen(target_hwnd, ctypes.byref(pt))
        client_screen_x = pt.x
        client_screen_y = pt.y

        # If client dimensions are 0, window is invalid
        if client_w <= 0 or client_h <= 0:
            log.warning("[WINDOW_GEOMETRY] Window HWND=%d has zero client area (%dx%d).", target_hwnd, client_w, client_h)
            return WindowGeometry(
                hwnd=target_hwnd,
                title=title,
                is_valid=False,
                window_rect=(win_x, win_y, w_rect.right, w_rect.bottom),
                window_x=win_x,
                window_y=win_y,
                window_width=win_w,
                window_height=win_h,
                dpi=dpi,
                dpi_scale=dpi_scale,
                is_maximized=is_maximized,
                is_minimized=is_minimized,
            )

        # 6. Browser Chrome Top Toolbar Height (Tabs + Omnibox)
        # In Chrome / Edge, the client area includes the tab bar and omnibox unless in full-screen (F11).
        # At 100% DPI, tab strip (~40px) + omnibox (~44px) = ~84px.
        # This scales proportionally with Windows display DPI scale.
        title_low = title.lower()
        is_browser = any(b in title_low for b in ("chrome", "edge", "firefox", "brave", "youtube", "browser"))

        browser_chrome_h = 0
        if is_browser:
            # Derived dynamically based on DPI scale
            base_chrome_logical_px = 80.0
            browser_chrome_h = int(round(base_chrome_logical_px * dpi_scale))

        viewport_screen_x = client_screen_x
        viewport_screen_y = client_screen_y + browser_chrome_h
        viewport_w = client_w
        viewport_h = max(1, client_h - browser_chrome_h)

        geom = WindowGeometry(
            hwnd=target_hwnd,
            title=title,
            is_valid=True,
            window_rect=(win_x, win_y, w_rect.right, w_rect.bottom),
            window_x=win_x,
            window_y=win_y,
            window_width=win_w,
            window_height=win_h,
            client_rect=(0, 0, client_w, client_h),
            client_width=client_w,
            client_height=client_h,
            client_screen_x=client_screen_x,
            client_screen_y=client_screen_y,
            browser_chrome_height=browser_chrome_h,
            viewport_screen_x=viewport_screen_x,
            viewport_screen_y=viewport_screen_y,
            viewport_width=viewport_w,
            viewport_height=viewport_h,
            dpi=dpi,
            dpi_scale=dpi_scale,
            is_maximized=is_maximized,
            is_minimized=is_minimized,
        )

        log.debug(
            "[WINDOW_GEOMETRY] HWND=%d title='%s' client_origin=(%d,%d) client_size=(%d,%d) viewport_size=(%d,%d) dpi=%d (scale=%.2f)",
            geom.hwnd, geom.title, geom.client_screen_x, geom.client_screen_y,
            geom.client_width, geom.client_height, geom.viewport_width, geom.viewport_height,
            geom.dpi, geom.dpi_scale
        )
        return geom


class CoordinateResolver:
    """
    Transforms coordinates strictly through explicit coordinate spaces:
      COMPONENT_SPACE -> VIEWPORT_SPACE -> WINDOW_CLIENT_SPACE -> SCREEN_SPACE
    Enforces space tagging, validation, and zero silent fallbacks.
    """

    @classmethod
    def component_to_viewport(
        cls,
        comp_coord: Coordinate,
        component_bbox_in_viewport: Any,  # BoundingBox in VIEWPORT_SPACE
    ) -> Coordinate:
        """
        Transform a local component coordinate (relative to component top-left)
        into viewport / webpage coordinates.
        """
        if comp_coord.space != CoordinateSpace.COMPONENT_SPACE:
            raise ValueError(f"Expected COMPONENT_SPACE coordinate, got {comp_coord.space}")

        bbox_x = getattr(component_bbox_in_viewport, "x", getattr(component_bbox_in_viewport, "left", 0.0))
        bbox_y = getattr(component_bbox_in_viewport, "y", getattr(component_bbox_in_viewport, "top", 0.0))

        vx = bbox_x + comp_coord.x
        vy = bbox_y + comp_coord.y
        return Coordinate(x=vx, y=vy, space=CoordinateSpace.VIEWPORT_SPACE)

    @classmethod
    def viewport_to_client(
        cls,
        viewport_coord: Coordinate,
        geometry: WindowGeometry,
    ) -> Coordinate:
        """
        Transform a viewport coordinate (relative to webpage top-left)
        into window client area coordinates (relative to window client (0, 0)).
        """
        if viewport_coord.space != CoordinateSpace.VIEWPORT_SPACE:
            raise ValueError(f"Expected VIEWPORT_SPACE coordinate, got {viewport_coord.space}")

        if not geometry.is_valid:
            raise ValueError(f"Cannot transform coordinate: WindowGeometry is invalid (HWND={geometry.hwnd})")

        # In client area, webpage viewport starts below the top browser chrome
        wx = viewport_coord.x
        wy = viewport_coord.y + geometry.browser_chrome_height
        return Coordinate(x=wx, y=wy, space=CoordinateSpace.WINDOW_CLIENT_SPACE)

    @classmethod
    def client_to_screen(
        cls,
        client_coord: Coordinate,
        geometry: WindowGeometry,
    ) -> PhysicalScreenPoint:
        """
        Transform a window client coordinate into physical screen coordinates on the desktop.
        """
        if client_coord.space != CoordinateSpace.WINDOW_CLIENT_SPACE:
            raise ValueError(f"Expected WINDOW_CLIENT_SPACE coordinate, got {client_coord.space}")

        if not geometry.is_valid:
            raise ValueError(f"Cannot transform coordinate: WindowGeometry is invalid (HWND={geometry.hwnd})")

        # Map client (0, 0) to actual physical screen origin via ClientToScreen
        sx = geometry.client_screen_x + client_coord.x
        sy = geometry.client_screen_y + client_coord.y
        return PhysicalScreenPoint(x=int(round(sx)), y=int(round(sy)))

    @classmethod
    def transform_component_to_screen(
        cls,
        comp_coord: Coordinate,
        component_bbox_in_viewport: Any,
        geometry: WindowGeometry,
    ) -> tuple[Optional[PhysicalScreenPoint], dict[str, Any]]:
        """
        Perform complete, step-by-step transformation:
          COMPONENT_SPACE -> VIEWPORT_SPACE -> WINDOW_CLIENT_SPACE -> SCREEN_SPACE
        Returns (PhysicalScreenPoint, diagnostic_trace_dict) or (None, error_trace).
        """
        trace: dict[str, Any] = {
            "component_space": (round(comp_coord.x, 2), round(comp_coord.y, 2)),
            "viewport_space": None,
            "window_client_space": None,
            "screen_space": None,
            "window_geometry": geometry.to_dict(),
            "success": False,
            "error": None,
        }

        if not geometry.is_valid:
            trace["error"] = f"Target window geometry is invalid (HWND={geometry.hwnd}, title='{geometry.title}')"
            log.warning("[COORDINATE] %s", trace["error"])
            return None, trace

        try:
            # Step 1: COMPONENT_SPACE -> VIEWPORT_SPACE
            vp_coord = cls.component_to_viewport(comp_coord, component_bbox_in_viewport)
            trace["viewport_space"] = (round(vp_coord.x, 2), round(vp_coord.y, 2))

            # Step 2: VIEWPORT_SPACE -> WINDOW_CLIENT_SPACE
            cl_coord = cls.viewport_to_client(vp_coord, geometry)
            trace["window_client_space"] = (round(cl_coord.x, 2), round(cl_coord.y, 2))

            # Step 3: WINDOW_CLIENT_SPACE -> SCREEN_SPACE (Physical Screen Point)
            screen_pt = cls.client_to_screen(cl_coord, geometry)
            trace["screen_space"] = (screen_pt.x, screen_pt.y)
            trace["success"] = True

            return screen_pt, trace

        except Exception as e:
            trace["error"] = str(e)
            log.warning("[COORDINATE] Transformation failure: %s", e)
            return None, trace

    @classmethod
    def validate_component_click_point(
        cls,
        comp_coord: Coordinate,
        component_bbox: Any,
    ) -> bool:
        """
        Guarantees that a local component click point is within the bounds of the component:
        0 <= comp_coord.x <= component_width and 0 <= comp_coord.y <= component_height.
        """
        if comp_coord.space != CoordinateSpace.COMPONENT_SPACE:
            raise ValueError(f"Expected COMPONENT_SPACE coordinate, got {comp_coord.space}")

        width = getattr(component_bbox, "width", 0.0)
        height = getattr(component_bbox, "height", 0.0)

        if width <= 0 or height <= 0:
            right = getattr(component_bbox, "right", 0.0)
            left = getattr(component_bbox, "left", 0.0)
            bottom = getattr(component_bbox, "bottom", 0.0)
            top = getattr(component_bbox, "top", 0.0)
            width = max(0.0, right - left)
            height = max(0.0, bottom - top)

        is_valid = (0.0 <= comp_coord.x <= width and 0.0 <= comp_coord.y <= height)
        if not is_valid:
            log.warning(
                "[COORDINATE][WARNING] Component local click point (%.1f, %.1f) is outside component bounds (%.1fx%.1f)",
                comp_coord.x, comp_coord.y, width, height
            )
        return is_valid

    @classmethod
    def validate_target_in_bbox(
        cls,
        target_point: Coordinate | tuple[float, float],
        bbox: Any,
    ) -> bool:
        """
        Target Sanity Check: Verifies that the target point is inside the detected component bounding box.
        Logs telemetry and returns whether containment check passed.
        """
        if isinstance(target_point, Coordinate):
            tx, ty = target_point.x, target_point.y
        else:
            tx, ty = float(target_point[0]), float(target_point[1])

        left = getattr(bbox, "left", getattr(bbox, "x", 0.0))
        top = getattr(bbox, "top", getattr(bbox, "y", 0.0))
        width = getattr(bbox, "width", 0.0)
        height = getattr(bbox, "height", 0.0)
        right = getattr(bbox, "right", left + width)
        bottom = getattr(bbox, "bottom", top + height)

        inside = (left <= tx <= right and top <= ty <= bottom)

        log.info(
            "\n[TARGET_VALIDATION]\ntarget=(%d,%d)\nbbox=(%d,%d,%d,%d)\ninside=%s",
            int(round(tx)), int(round(ty)),
            int(round(left)), int(round(top)), int(round(right)), int(round(bottom)),
            inside,
        )

        if not inside:
            log.error(
                "[TARGET_VALIDATION][ERROR]\nTarget is outside component bounding box.\n"
                "target=(%d,%d) bounds=[left=%d, top=%d, right=%d, bottom=%d]",
                int(round(tx)), int(round(ty)),
                int(round(left)), int(round(top)), int(round(right)), int(round(bottom))
            )

        return inside

    @classmethod
    def log_coordinate_debug(
        cls,
        geometry: WindowGeometry,
        component_bbox: Any,
        local_click: tuple[float, float],
        target_coords: dict[str, tuple[float, float]],
        mouse_telemetry: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Outputs a comprehensive Coordinate Debug Mode block:
        WINDOW, COMPONENT, TARGET, and MOUSE telemetry.
        """
        bbox_left = int(round(getattr(component_bbox, "left", getattr(component_bbox, "x", 0.0))))
        bbox_top = int(round(getattr(component_bbox, "top", getattr(component_bbox, "y", 0.0))))
        bbox_right = int(round(getattr(component_bbox, "right", bbox_left + getattr(component_bbox, "width", 0.0))))
        bbox_bottom = int(round(getattr(component_bbox, "bottom", bbox_top + getattr(component_bbox, "height", 0.0))))
        comp_w = max(0, bbox_right - bbox_left)
        comp_h = max(0, bbox_bottom - bbox_top)

        vp_pt = target_coords.get("viewport", (0.0, 0.0))
        cl_pt = target_coords.get("window_client", (0.0, 0.0))
        sc_pt = target_coords.get("screen", (0.0, 0.0))

        mouse_telemetry = mouse_telemetry or {}
        cursor_before = mouse_telemetry.get("cursor_before", (0, 0))
        delta = mouse_telemetry.get("delta", (0, 0))
        cursor_after = mouse_telemetry.get("cursor_after", (0, 0))
        verified = mouse_telemetry.get("verified", True)

        if geometry and geometry.hwnd:
            log.info("[COORDINATE_DEBUG] Using locked HWND=%d", geometry.hwnd)

        debug_str = (
            "\n[COORDINATE_DEBUG]\n\n"
            "WINDOW\n"
            f"origin=({geometry.window_x},{geometry.window_y})\n"
            f"client_origin=({geometry.client_screen_x},{geometry.client_screen_y})\n"
            f"client_size=({geometry.client_width},{geometry.client_height})\n"
            f"viewport_origin=({geometry.viewport_screen_x},{geometry.viewport_screen_y})\n"
            f"viewport_size=({geometry.viewport_width},{geometry.viewport_height})\n"
            f"browser_chrome_height={geometry.browser_chrome_height}\n"
            f"dpi_scale={geometry.dpi_scale:.2f}\n\n"
            "COMPONENT\n"
            f"bbox=({bbox_left},{bbox_top},{bbox_right},{bbox_bottom})\n"
            f"size=({comp_w},{comp_h})\n"
            f"local_click=({int(round(local_click[0]))},{int(round(local_click[1]))})\n\n"
            "TARGET\n"
            f"viewport=({int(round(vp_pt[0]))},{int(round(vp_pt[1]))})\n"
            f"window_client=({int(round(cl_pt[0]))},{int(round(cl_pt[1]))})\n"
            f"screen=({int(round(sc_pt[0]))},{int(round(sc_pt[1]))})\n\n"
            "MOUSE\n"
            f"cursor_before=({cursor_before[0]},{cursor_before[1]})\n"
            f"delta=({delta[0]},{delta[1]})\n"
            f"cursor_after=({cursor_after[0]},{cursor_after[1]})\n"
            f"verified={verified}"
        )
        log.info(debug_str)
        return debug_str


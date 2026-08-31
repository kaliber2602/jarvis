"""
Screenshot and Screen/Window Perception Manager.
Captures screen/window visuals, maps coordinates across viewport spaces,
and calculates visual frame stability scores.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional, Tuple

try:
    from PIL import Image, ImageChops, ImageGrab, ImageStat
except ImportError:
    Image = None
    ImageGrab = None
    ImageChops = None
    ImageStat = None

from .coordinates import CoordinateSpace, WindowGeometry, WindowGeometryProvider
from .models import BoundingBox, Point

log = logging.getLogger("hermes_ui.screenshot_manager")

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
else:
    user32 = None


class ScreenshotManager:
    """
    Manages screenshot capture, coordinate space conversions, and visual stability monitoring.
    """

    def __init__(self):
        self.last_capture: Optional[Any] = None
        self.last_capture_time: float = 0.0
        self._cached_window_rect: Optional[BoundingBox] = None

    def capture_screen(self, bbox: Optional[Tuple[int, int, int, int]] = None) -> Optional[Any]:
        """
        Capture the entire screen or a specific bounding box (left, top, right, bottom).
        """
        if ImageGrab is None:
            log.warning("[SCREENSHOT] PIL ImageGrab is not available.")
            return None

        try:
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
            self.last_capture = img
            self.last_capture_time = time.time()
            return img
        except Exception as e:
            log.warning("[SCREENSHOT] Error capturing screen: %s", e)
            return None

    def capture_active_window(self, hwnd: Optional[int] = None) -> Tuple[Optional[Any], BoundingBox, dict[str, Any]]:
        """
        Capture the active foreground window and return (image, window_bbox, window_metadata).
        """
        win_info = self.get_active_window_geometry(hwnd=hwnd)
        w_bbox = win_info["bbox"]

        if w_bbox.width <= 0 or w_bbox.height <= 0 or ImageGrab is None:
            # Fallback to full screen
            img = self.capture_screen()
            sw = self.get_screen_width()
            sh = self.get_screen_height()
            return img, BoundingBox(0, 0, sw, sh, space=CoordinateSpace.SCREEN_SPACE), win_info

        try:
            bbox_tuple = (
                int(w_bbox.left),
                int(w_bbox.top),
                int(w_bbox.right),
                int(w_bbox.bottom),
            )
            img = ImageGrab.grab(bbox=bbox_tuple, all_screens=True)
            self.last_capture = img
            self.last_capture_time = time.time()
            return img, w_bbox, win_info
        except Exception as e:
            log.debug("[SCREENSHOT] Window grab fallback to full screen: %s", e)
            img = self.capture_screen()
            return img, w_bbox, win_info

    def get_screen_width(self) -> int:
        if sys.platform == "win32" and user32:
            return user32.GetSystemMetrics(0)
        return 1920

    def get_screen_height(self) -> int:
        if sys.platform == "win32" and user32:
            return user32.GetSystemMetrics(1)
        return 1080

    def get_active_window_geometry(self, hwnd: Optional[int] = None) -> dict[str, Any]:
        """
        Inspect the active foreground window HWND, title, and bounding rectangle using WindowGeometryProvider.
        """
        geom: WindowGeometry = WindowGeometryProvider.get_window_geometry(hwnd=hwnd)

        sw = self.get_screen_width()
        sh = self.get_screen_height()

        if not geom.is_valid:
            return {
                "hwnd": geom.hwnd,
                "title": geom.title,
                "app": "generic",
                "bbox": BoundingBox(0, 0, sw, sh, space=CoordinateSpace.SCREEN_SPACE),
                "is_browser": False,
                "is_youtube": False,
                "geometry": geom,
            }

        title_low = geom.title.lower()
        is_youtube = "youtube" in title_low
        is_browser = any(b in title_low for b in ("chrome", "google chrome", "edge", "firefox", "brave", "youtube"))
        app_name = "chrome" if is_browser else ("vscode" if "code" in title_low else "unknown")

        w_bbox = BoundingBox(
            x=geom.window_x,
            y=geom.window_y,
            width=geom.window_width,
            height=geom.window_height,
            space=CoordinateSpace.SCREEN_SPACE,
        )

        return {
            "hwnd": geom.hwnd,
            "title": geom.title,
            "app": app_name,
            "bbox": w_bbox,
            "is_browser": is_browser,
            "is_youtube": is_youtube,
            "geometry": geom,
        }

    def compute_stability_score(self, img_before: Optional[Any], img_after: Optional[Any]) -> float:
        """
        Compute visual stability score between two consecutive frames [0.0 to 1.0].
        Score of 1.0 indicates completely stable (no layout shifts/animations),
        while < 0.85 indicates rapid changes (loading skeletons, animated dropdowns, video playback).
        """
        if img_before is None or img_after is None or ImageChops is None or ImageStat is None:
            return 1.0

        try:
            # Resize for fast comparison
            size = (256, 144)
            b_small = img_before.convert("RGB").resize(size)
            a_small = img_after.convert("RGB").resize(size)

            diff = ImageChops.difference(b_small, a_small)
            stat = ImageStat.Stat(diff)
            mean_diff = sum(stat.mean) / len(stat.mean)  # 0 to 255

            # Normalize to stability [0.0, 1.0]
            # Mean diff of 0 -> stability 1.0; mean diff of 50+ -> stability ~0.0
            stability = max(0.0, min(1.0, 1.0 - (mean_diff / 50.0)))
            return float(stability)
        except Exception as e:
            log.debug("[SCREENSHOT] Error computing stability score: %s", e)
            return 1.0

    def wait_for_ui_stability(self, max_wait: float = 2.0, min_score: float = 0.90) -> float:
        """
        Poll screenshots until visual stability threshold is reached or timeout occurs.
        """
        start = time.time()
        prev_img = self.capture_screen()
        time.sleep(0.15)

        stability = 1.0
        while time.time() - start < max_wait:
            curr_img = self.capture_screen()
            stability = self.compute_stability_score(prev_img, curr_img)
            if stability >= min_score:
                break
            prev_img = curr_img
            time.sleep(0.15)

        return stability

    @staticmethod
    def normalized_to_screen_pixels(
        norm_x: float,
        norm_y: float,
        window_bbox: Optional[BoundingBox] = None,
        screen_w: int = 1920,
        screen_h: int = 1080,
    ) -> Tuple[int, int]:
        """
        Convert normalized coordinate [0.0, 1.0] relative to a window bbox (or screen) into screen pixels.
        """
        if window_bbox and window_bbox.width > 0 and window_bbox.height > 0:
            px = int(window_bbox.left + window_bbox.width * norm_x)
            py = int(window_bbox.top + window_bbox.height * norm_y)
        else:
            px = int(screen_w * norm_x)
            py = int(screen_h * norm_y)
        return (px, py)

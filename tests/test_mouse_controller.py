"""
Comprehensive Unit Tests for Mouse Controller, Cursor Awareness, Precision Movement,
Coordinate Spaces, Component Click Validation, Target Containment, and Telemetry.
"""

from __future__ import annotations

import logging
import math
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.mouse_controller import MouseController, MousePosition
from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.ui_perception.coordinates import (
    Coordinate,
    CoordinateResolver,
    CoordinateSpace,
    PhysicalScreenPoint,
    WindowGeometry,
    WindowGeometryProvider,
)
from agent.ui_perception.models import BoundingBox, ElementType, UIElement


class TestMouseController(unittest.TestCase):

    def setUp(self):
        # Reset mouse controller state before each test
        MouseController._cached_position = None
        MouseController.set_simulated_position(100, 200)

    def test_mouse_position_dataclass(self):
        """Test MousePosition fields, serialization, and conversions."""
        pos = MousePosition(x=500, y=300, timestamp=123456.789, screen_id=1, dpi_scale=1.25)
        self.assertEqual(pos.x, 500)
        self.assertEqual(pos.y, 300)
        self.assertEqual(pos.to_tuple(), (500, 300))
        d = pos.to_dict()
        self.assertEqual(d["x"], 500)
        self.assertEqual(d["y"], 300)
        self.assertEqual(d["screen_id"], 1)
        self.assertAlmostEqual(d["dpi_scale"], 1.25, places=2)

    def test_get_cursor_position_fresh_vs_cached(self):
        """Test that force_fresh always queries new position and cache honors MAX_MOUSE_STATE_AGE."""
        MouseController.set_simulated_position(250, 450)
        pos1 = MouseController.get_cursor_position(force_fresh=True)
        self.assertEqual(pos1.to_tuple(), (250, 450))

        # Change simulated position
        MouseController._simulated_position = (800, 600)

        # Non-fresh query within 100ms should return cached
        pos_cached = MouseController.get_cursor_position(force_fresh=False)
        self.assertEqual(pos_cached.to_tuple(), (250, 450))

        # Fresh query must return updated position
        pos_fresh = MouseController.get_cursor_position(force_fresh=True)
        self.assertEqual(pos_fresh.to_tuple(), (800, 600))

    def test_no_guessed_cursor_position(self):
        """Cursor position must strictly reflect OS/simulated state, never center or last target."""
        MouseController.set_simulated_position(42, 99)
        pos = MouseController.get_cursor_position(force_fresh=True)
        self.assertEqual(pos.x, 42)
        self.assertEqual(pos.y, 99)

        # Ensure it does not default to 1920/2, 1080/2
        self.assertNotEqual(pos.to_tuple(), (960, 540))

    def test_movement_and_verification_success(self):
        """Test smooth movement from cursor_before to target with verification success."""
        MouseController.set_simulated_position(100, 100)
        res = MouseController.move(target_x=400, target_y=500, tolerance=2)

        self.assertTrue(res["success"])
        self.assertTrue(res["verified"])
        self.assertEqual(res["cursor_before"], (100, 100))
        self.assertEqual(res["cursor_after"], (400, 500))
        self.assertEqual(res["target"], (400, 500))
        self.assertEqual(res["delta"], (300, 400))
        self.assertEqual(res["distance"], 500.0)

    def test_movement_verification_failure_logged(self):
        """Test when physical cursor does not reach target within tolerance."""
        MouseController.set_simulated_position(100, 100)

        # Mock get_cursor_position after move to return an offset position (e.g. 410, 510)
        original_get_pos = MouseController.get_cursor_position

        def mock_get_pos(force_fresh=True):
            # First call (before): (100, 100), Second call (after): (410, 510)
            if not hasattr(mock_get_pos, "called"):
                mock_get_pos.called = True
                return MousePosition(x=100, y=100, timestamp=time.time())
            return MousePosition(x=410, y=510, timestamp=time.time())

        with patch.object(MouseController, "get_cursor_position", side_effect=mock_get_pos):
            res = MouseController.move(target_x=400, target_y=500, tolerance=2)
            self.assertFalse(res["verified"])
            self.assertFalse(res["success"])
            self.assertEqual(res["cursor_after"], (410, 510))

    def test_click_telemetry_and_distinct_verification(self):
        """Test click execution returns mouse_action_success and target_interaction_verified."""
        MouseController.set_simulated_position(200, 300)
        res = MouseController.click(target_x=767, target_y=293, click_count=1)

        self.assertTrue(res["success"])
        self.assertTrue(res["mouse_action_success"])
        # target_interaction_verified must be False by default until visual perception confirms
        self.assertFalse(res["target_interaction_verified"])
        self.assertEqual(res["click_point"], (767, 293))
        self.assertEqual(res["click_count"], 1)
        self.assertIn("move_telemetry", res)
        self.assertTrue(res["move_telemetry"]["verified"])

    def test_double_click_and_right_click(self):
        """Test double_click and right_click helpers."""
        MouseController.set_simulated_position(0, 0)
        res_dbl = MouseController.double_click(300, 400)
        self.assertTrue(res_dbl["success"])
        self.assertEqual(res_dbl["click_count"], 2)
        self.assertEqual(res_dbl["button"], "left")

        res_rgt = MouseController.right_click(500, 600)
        self.assertTrue(res_rgt["success"])
        self.assertEqual(res_rgt["click_count"], 1)
        self.assertEqual(res_rgt["button"], "right")

    def test_mouse_down_mouse_up_drag(self):
        """Test mouse_down, mouse_up, and drag operations."""
        MouseController.set_simulated_position(100, 100)
        res_down = MouseController.mouse_down()
        self.assertTrue(res_down["success"])
        self.assertEqual(res_down["position"], (100, 100))

        res_up = MouseController.mouse_up()
        self.assertTrue(res_up["success"])

        res_drag = MouseController.drag(start_x=100, start_y=100, end_x=500, end_y=600)
        self.assertTrue(res_drag["success"])
        self.assertEqual(res_drag["start"], (100, 100))
        self.assertEqual(res_drag["end"], (500, 600))

    def test_component_click_point_validation(self):
        """Test validation of local component click coordinates within component bbox."""
        bbox = BoundingBox(x=546, y=104, width=442, height=336, space=CoordinateSpace.VIEWPORT_SPACE)

        # Valid local coordinate
        valid_local = Coordinate(x=221, y=109, space=CoordinateSpace.COMPONENT_SPACE)
        self.assertTrue(CoordinateResolver.validate_component_click_point(valid_local, bbox))

        # Invalid local coordinate (out of bounds)
        invalid_local = Coordinate(x=500, y=109, space=CoordinateSpace.COMPONENT_SPACE)
        self.assertFalse(CoordinateResolver.validate_component_click_point(invalid_local, bbox))

        invalid_negative = Coordinate(x=-10, y=50, space=CoordinateSpace.COMPONENT_SPACE)
        self.assertFalse(CoordinateResolver.validate_component_click_point(invalid_negative, bbox))

    def test_target_containment_sanity_check(self):
        """Test Target Sanity Check: verifies point is inside bbox and warns/errors if outside."""
        bbox = BoundingBox(x=546, y=104, width=442, height=336, space=CoordinateSpace.VIEWPORT_SPACE)

        # Inside target point (767, 213)
        inside_pt = Coordinate(x=767, y=213, space=CoordinateSpace.VIEWPORT_SPACE)
        self.assertTrue(CoordinateResolver.validate_target_in_bbox(inside_pt, bbox))

        # Outside target point (500, 50) - above and to the left
        outside_pt = Coordinate(x=500, y=50, space=CoordinateSpace.VIEWPORT_SPACE)
        self.assertFalse(CoordinateResolver.validate_target_in_bbox(outside_pt, bbox))

        # Outside target point (1000, 300) - to the right
        outside_pt2 = Coordinate(x=1000, y=300, space=CoordinateSpace.VIEWPORT_SPACE)
        self.assertFalse(CoordinateResolver.validate_target_in_bbox(outside_pt2, bbox))

    def test_coordinate_debug_mode_logging(self):
        """Test structured [COORDINATE_DEBUG] block output."""
        geom = WindowGeometry(
            hwnd=123,
            title="YouTube - Chrome",
            is_valid=True,
            window_rect=(0, 0, 1920, 1032),
            window_x=0,
            window_y=0,
            window_width=1920,
            window_height=1032,
            client_rect=(0, 0, 1920, 1032),
            client_width=1920,
            client_height=1032,
            client_screen_x=0,
            client_screen_y=0,
            browser_chrome_height=80,
            viewport_screen_x=0,
            viewport_screen_y=80,
            viewport_width=1920,
            viewport_height=952,
            dpi=96,
            dpi_scale=1.0,
        )
        bbox = BoundingBox(x=546, y=104, width=442, height=336, space=CoordinateSpace.VIEWPORT_SPACE)
        local_click = (221.0, 109.0)
        target_coords = {
            "viewport": (767.0, 213.0),
            "window_client": (767.0, 293.0),
            "screen": (767.0, 293.0),
        }
        mouse_telemetry = {
            "cursor_before": (1240, 680),
            "delta": (-473, -387),
            "cursor_after": (767, 293),
            "verified": True,
        }

        output = CoordinateResolver.log_coordinate_debug(
            geometry=geom,
            component_bbox=bbox,
            local_click=local_click,
            target_coords=target_coords,
            mouse_telemetry=mouse_telemetry,
        )

        self.assertIn("[COORDINATE_DEBUG]", output)
        self.assertIn("WINDOW", output)
        self.assertIn("COMPONENT", output)
        self.assertIn("TARGET", output)
        self.assertIn("MOUSE", output)
        self.assertIn("cursor_before=(1240,680)", output)
        self.assertIn("cursor_after=(767,293)", output)
        self.assertIn("verified=True", output)

    def test_youtube_video_selection_mouse_integration(self):
        """
        Verify that select_youtube_video executes full pipeline:
        cursor_before query -> human-like move -> verify -> click -> distinct verification state.
        """
        geom = WindowGeometry(
            hwnd=12345,
            title="YouTube - Google Chrome",
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

        from agent.tools.window_target_resolver import BrowserSession, BrowserSessionState, WindowTargetResolver
        from agent.ui_perception.models import UITree
        from agent.ui_perception.service import HermesUIService

        session = BrowserSession(
            process_name="chrome.exe",
            pid=12345,
            hwnd=12345,
            title="YouTube - Google Chrome",
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)

        mock_tree = UITree(
            screen_width=1920,
            screen_height=1080,
            window_title="YouTube - Google Chrome",
            app_name="chrome",
            is_browser=True,
            stability_score=1.0,
        )
        for i in range(1, 4):
            elem = UIElement(
                id=f"yt_video_card_{i}",
                text=f"Video {i}",
                type=ElementType.VIDEO_CARD,
                bbox=BoundingBox(x=50.0 + (i - 1) * 450.0, y=104.0, width=420.0, height=280.0, space=CoordinateSpace.VIEWPORT_SPACE),
                interactive=True,
            )
            mock_tree.elements[elem.id] = elem

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(True, "VALID")), \
             patch.object(HermesUIService, "perceive_active_window", return_value=mock_tree), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom):

            MouseController.set_simulated_position(1240, 680)
            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)

            self.assertFalse(res["success"])
            self.assertTrue(res["mouse_action_success"])
            self.assertFalse(res["target_interaction_verified"])
            self.assertFalse(res["task_verified"])
            self.assertEqual(res["target_id"], "yt_video_card_2")
            self.assertEqual(res["cursor_before"], (1240, 680))
            self.assertEqual(res["click_point"], (res["cursor_after"][0], res["cursor_after"][1]))
            self.assertTrue(res["movement_verified"])


if __name__ == "__main__":
    unittest.main()

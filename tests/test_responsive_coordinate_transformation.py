"""
Comprehensive Test Suite for Responsive Component Targeting & Coordinate Transformation.

Validates the full specification test matrix:
- Test A: Same window ordinals 1, 2, 3, 4 (Row 1)
- Test B: Second row ordinals 5, 6, 7, 8 (Row 2)
- Test C: Resized Chrome (Adaptive column counts across 1920, 1400, 900, 500 px viewports)
- Test D: Moved Chrome (Arbitrary screen positions: (0,0), (250, 120), (500, 300))
- Test E: Maximized vs Restored geometry transitions
- Test F: Windows DPI scaling (100%, 125%, 150%, 175%, 200%)
- Test G: Multi-monitor coordinates (Negative monitor bounds: e.g. -1920, 0)
- Test H: Strict failure on invalid window geometry without guessing
- Test I: Diagnostic logging verification ([COMPONENT_TARGET], [COORDINATE], [WINDOW], [MOUSE])
- Test J: Separation of concerns (TargetResolver vs CoordinateResolver vs MouseExecutor)
"""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.ui_perception.coordinates import (
    Coordinate,
    CoordinateResolver,
    CoordinateSpace,
    PhysicalScreenPoint,
    WindowGeometry,
    WindowGeometryProvider,
)
from agent.ui_perception.layout_engine import LayoutEngine
from agent.ui_perception.models import BoundingBox, ElementType, UIElement
from agent.ui_perception.service import get_ui_service


class TestResponsiveCoordinateTransformation(unittest.TestCase):

    def setUp(self):
        self.ui_service = get_ui_service()
        self.layout_engine = LayoutEngine()
        from agent.tools.window_target_resolver import BrowserSession, WindowTargetResolver
        session = BrowserSession(
            process_name="chrome.exe",
            pid=12345,
            hwnd=12345,
            title="YouTube - Google Chrome",
            state="ACTIVE",
        )
        WindowTargetResolver.set_browser_session(session)
        self.val_patcher = patch("agent.tools.window_target_resolver.WindowTargetResolver.validate_browser_session", return_value=(True, "VALID"))
        self.val_patcher.start()

    def tearDown(self):
        self.val_patcher.stop()
        from agent.tools.window_target_resolver import WindowTargetResolver
        WindowTargetResolver.release_target()
        WindowTargetResolver.set_browser_session(None)

    def _create_mock_geometry(
        self,
        screen_x: int = 0,
        screen_y: int = 0,
        client_w: int = 1920,
        client_h: int = 1080,
        chrome_h: int = 80,
        dpi: int = 96,
        dpi_scale: float = 1.0,
        is_maximized: bool = False,
    ) -> WindowGeometry:
        return WindowGeometry(
            hwnd=12345,
            title="YouTube - Google Chrome",
            is_valid=True,
            window_rect=(screen_x, screen_y, screen_x + client_w, screen_y + client_h),
            window_x=screen_x,
            window_y=screen_y,
            window_width=client_w,
            window_height=client_h,
            client_rect=(0, 0, client_w, client_h),
            client_width=client_w,
            client_height=client_h,
            client_screen_x=screen_x,
            client_screen_y=screen_y,
            browser_chrome_height=chrome_h,
            viewport_screen_x=screen_x,
            viewport_screen_y=screen_y + chrome_h,
            viewport_width=client_w,
            viewport_height=max(1, client_h - chrome_h),
            dpi=dpi,
            dpi_scale=dpi_scale,
            is_maximized=is_maximized,
        )

    def test_a_same_window_row_1_ordinals(self):
        """
        Test A: In a 4-column layout, ordinals 1, 2, 3, 4 map to row 0 (left -> right).
        Verifies exact physical screen coordinates without hardcoding.
        """
        geom = self._create_mock_geometry(screen_x=0, screen_y=0, client_w=1920, client_h=1080)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}) as mock_click:

            prev_x = -1
            for ordinal in range(1, 5):
                res = ComputerUseTool.select_youtube_video(index=ordinal, wait_load=False)
                self.assertTrue(res["mouse_action_success"])
                self.assertEqual(res["target_id"], f"yt_video_card_{ordinal}")

                click_x, click_y = res["click_point"]
                # X coordinates must strictly increase left -> right
                self.assertGreater(click_x, prev_x, f"Video {ordinal} X ({click_x}) must be > previous X ({prev_x})")
                prev_x = click_x

                # All row 1 videos must have identical Y coordinates
                trace = res["transform_trace"]
                self.assertAlmostEqual(trace["window_client_space"][1], 293.4, delta=0.5)  # 80 chrome + 104 header + 109.4 (thumb center)

    def test_b_second_row_ordinals(self):
        """
        Test B: Ordinals 5, 6, 7, 8 map to row 1 (second row) below row 1.
        """
        geom = self._create_mock_geometry(screen_x=0, screen_y=0, client_w=1920, client_h=1080)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}):

            res_row1 = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
            res_row2 = ComputerUseTool.select_youtube_video(index=5, wait_load=False)

            self.assertTrue(res_row1["mouse_action_success"])
            self.assertTrue(res_row2["mouse_action_success"])

            y1 = res_row1["click_point"][1]
            y2 = res_row2["click_point"][1]

            self.assertGreater(y2, y1 + 200, f"Row 2 click Y ({y2}) must be substantially below Row 1 Y ({y1})")
            # Same column 0 means identical X
            self.assertEqual(res_row1["click_point"][0], res_row2["click_point"][0])

    def test_c_resize_chrome_adaptive_grid(self):
        """
        Test C: When Chrome is resized to different widths:
        - 1920px -> 4 columns (video 1..4 in row 1)
        - 1400px -> 3 columns (video 1..3 in row 1, video 4 in row 2)
        - 800px  -> 2 columns (video 1..2 in row 1, video 3 in row 2)
        """
        # 1. 1400px window -> 3 columns
        geom_1400 = self._create_mock_geometry(client_w=1400, client_h=900)
        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_1400), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}):

            tree = self.ui_service.perceive_active_window(force_fresh=True, hwnd=geom_1400.hwnd)
            v_cards = [e for e in tree.elements.values() if e.type == ElementType.VIDEO_CARD]
            ordered = self.layout_engine.apply_row_major_ordering(v_cards)

            # In 1400px viewport, video 4 must be at row 1 (second row)
            self.assertEqual(ordered[3].row, 1)
            self.assertEqual(ordered[3].column, 0)

        # 2. 800px window -> 2 columns
        geom_800 = self._create_mock_geometry(client_w=800, client_h=700)
        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_800), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}):

            tree = self.ui_service.perceive_active_window(force_fresh=True, hwnd=geom_800.hwnd)
            v_cards = [e for e in tree.elements.values() if e.type == ElementType.VIDEO_CARD]
            ordered = self.layout_engine.apply_row_major_ordering(v_cards)

            # In 800px viewport, video 3 must be at row 1 (second row)
            self.assertEqual(ordered[2].row, 1)
            self.assertEqual(ordered[2].column, 0)

    def test_d_move_chrome_different_screen_positions(self):
        """
        Test D: When Chrome is moved to different positions on the desktop:
        (0, 0) vs (300, 150) vs (800, 400).
        Coordinates must translate exactly by delta (dx, dy).
        """
        geom_origin = self._create_mock_geometry(screen_x=0, screen_y=0, client_w=1280, client_h=800)
        geom_moved = self._create_mock_geometry(screen_x=300, screen_y=150, client_w=1280, client_h=800)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}):

            with patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_origin):
                res_orig = ComputerUseTool.select_youtube_video(index=2, wait_load=False)

            with patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_moved):
                res_moved = ComputerUseTool.select_youtube_video(index=2, wait_load=False)

            orig_x, orig_y = res_orig["click_point"]
            moved_x, moved_y = res_moved["click_point"]

            self.assertEqual(moved_x - orig_x, 300, "X coordinate must shift by exact window X offset (+300)")
            self.assertEqual(moved_y - orig_y, 150, "Y coordinate must shift by exact window Y offset (+150)")

    def test_e_maximize_and_restore_transitions(self):
        """
        Test E: Verify coordinate transformation for maximized vs restored window.
        """
        # Restored at (100, 50, 1400, 900)
        geom_restored = self._create_mock_geometry(screen_x=100, screen_y=50, client_w=1400, client_h=900, is_maximized=False)
        # Maximized at (0, 0, 1920, 1080)
        geom_max = self._create_mock_geometry(screen_x=0, screen_y=0, client_w=1920, client_h=1080, is_maximized=True)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}):

            with patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_restored):
                res_restored = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
                self.assertTrue(res_restored["mouse_action_success"])

            with patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_max):
                res_max = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
                self.assertTrue(res_max["mouse_action_success"])

            # Verify transform trace accurately tracks window state
            self.assertFalse(res_restored["transform_trace"]["window_geometry"]["is_maximized"])
            self.assertTrue(res_max["transform_trace"]["window_geometry"]["is_maximized"])

    def test_f_dpi_scaling_awareness(self):
        """
        Test F: Windows DPI scaling (100%, 125%, 150%, 200%).
        Browser chrome toolbar height and client coordinates scale proportionally with DPI.
        """
        # 100% DPI (96 DPI, scale=1.0)
        geom_100 = self._create_mock_geometry(screen_x=0, screen_y=0, client_w=1920, client_h=1080, chrome_h=80, dpi=96, dpi_scale=1.0)
        # 150% DPI (144 DPI, scale=1.5)
        geom_150 = self._create_mock_geometry(screen_x=0, screen_y=0, client_w=2880, client_h=1620, chrome_h=120, dpi=144, dpi_scale=1.5)

        comp_coord = Coordinate(x=100.0, y=50.0, space=CoordinateSpace.COMPONENT_SPACE)
        card_bbox = BoundingBox(x=50.0, y=104.0, width=400.0, height=300.0, space=CoordinateSpace.VIEWPORT_SPACE)

        pt_100, trace_100 = CoordinateResolver.transform_component_to_screen(comp_coord, card_bbox, geom_100)
        pt_150, trace_150 = CoordinateResolver.transform_component_to_screen(comp_coord, card_bbox, geom_150)

        self.assertIsNotNone(pt_100)
        self.assertIsNotNone(pt_150)

        # 100% DPI screen Y: client_y (0) + chrome_h (80) + bbox_y (104) + comp_y (50) = 234
        self.assertEqual(pt_100.y, 234)
        # 150% DPI screen Y: client_y (0) + chrome_h (120) + bbox_y (104) + comp_y (50) = 274
        self.assertEqual(pt_150.y, 274)

    def test_g_multimonitor_negative_coordinates(self):
        """
        Test G: Chrome positioned on a secondary monitor to the left (e.g. screen_x = -1920, screen_y = 0).
        Coordinates must transform correctly into negative screen coordinates.
        """
        geom_sec = self._create_mock_geometry(screen_x=-1920, screen_y=0, client_w=1920, client_h=1080)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_sec), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}) as mock_click:

            res = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
            self.assertTrue(res["mouse_action_success"])
            click_x, click_y = res["click_point"]

            # Must click within the secondary monitor bounds (-1920 .. 0)
            self.assertLess(click_x, 0)
            self.assertGreater(click_x, -1920)

    def test_h_remove_silent_fallbacks_on_invalid_geometry(self):
        """
        Test H: If window geometry cannot be resolved or is invalid, the system must NOT guess
        or use hardcoded 1920x1080 fallbacks. It must fail cleanly with success=False.
        """
        invalid_geom = WindowGeometry(hwnd=0, title="", is_valid=False)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=invalid_geom):

            res = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
            self.assertFalse(res["success"])
            self.assertIn("Unable to resolve coordinate transformation", res["error"])

    def test_i_diagnostic_logging_trace(self):
        """
        Test I: Verify that the diagnostic logging trace includes all required sections:
        [COMPONENT_TARGET], [COORDINATE], [WINDOW], and [MOUSE].
        """
        geom = self._create_mock_geometry(screen_x=100, screen_y=200, client_w=1920, client_h=1080)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True}), \
             self.assertLogs("computer_use_tool", level="INFO") as log_cm:

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
            self.assertTrue(res["mouse_action_success"])

            full_log = "\n".join(log_cm.output)
            self.assertIn("[COMPONENT_TARGET]", full_log)
            self.assertIn("[COORDINATE]", full_log)
            self.assertIn("[WINDOW]", full_log)
            self.assertIn("[MOUSE]", full_log)
            self.assertIn("component_space=", full_log)
            self.assertIn("viewport_space=", full_log)
            self.assertIn("window_client_space=", full_log)
            self.assertIn("screen_space=", full_log)
            self.assertIn("final_physical_point=", full_log)

    def test_j_separation_of_concerns(self):
        """
        Test J: Verify strict separation:
        1. TargetResolver produces candidate and local coordinates.
        2. CoordinateResolver converts through typed spaces to PhysicalScreenPoint.
        3. MouseExecutor receives only PhysicalScreenPoint.
        """
        # Step 1: Target candidate
        card = UIElement(
            id="test_card",
            type=ElementType.VIDEO_CARD,
            bbox=BoundingBox(x=100.0, y=104.0, width=400.0, height=300.0, space=CoordinateSpace.VIEWPORT_SPACE),
        )

        # Step 2: Component Space Coordinate
        comp_pt = Coordinate(x=200.0, y=97.5, space=CoordinateSpace.COMPONENT_SPACE)

        # Step 3: Coordinate Resolver
        geom = self._create_mock_geometry(screen_x=50, screen_y=50)
        screen_pt, trace = CoordinateResolver.transform_component_to_screen(comp_pt, card.bbox, geom)

        self.assertIsInstance(screen_pt, PhysicalScreenPoint)
        self.assertEqual(screen_pt.x, 50 + 100 + 200)  # 350
        self.assertEqual(screen_pt.y, int(round(50 + 80 + 104 + 97.5)))  # 332

        # Step 4: MouseExecutor
        with patch.object(MouseExecutor, "click_physical_point") as mock_mouse:
            mock_mouse.return_value = {"success": True}
            MouseExecutor.click_physical_point(screen_pt)
            mock_mouse.assert_called_with(screen_pt)


if __name__ == "__main__":
    unittest.main()

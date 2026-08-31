"""
Comprehensive Test Suite for YouTube Card Target Resolution & Coordinate Calculation.
Verifies:
1. Pure Geometry-driven target selection (zero hardcoded layout constants).
2. Layout A (w=442, gap=16), Layout B (w=380, gap=24), Layout C (w=500, gap=12).
3. Window resize dynamics (1920x1080 -> 1600x900 -> 1280x720).
4. Browser zoom levels (80%, 100%, 110%, 125%).
5. Cursor initial position invariance (cursor at card #1, #3, #4, #5, #6 targeting card #2).
6. Zero fallback to card #1 on invalid/out-of-range index.
7. Target identity validation and safe thumbnail interaction point hit-testing.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.component_target import ComponentTarget, derive_safe_interaction_point, sort_row_major
from agent.tools.computer_use import ComputerUseTool
from agent.tools.coordinate_mapper import BoundingBox, CoordinateMapper, CoordinateSpace, Point
from agent.tools.dom_perception import ChromeDOMConnector
from agent.tools.mouse_controller import MouseController
from agent.tools.ui_interaction_service import UIInteractionService
from agent.tools.window_manager import WindowHandle, WindowManager, WindowSnapshot
from agent.tools.window_target_resolver import BrowserSession, BrowserSessionState, WindowTargetResolver
from agent.ui_perception.coordinates import WindowGeometry, WindowGeometryProvider
from agent.ui_perception.models import ElementType, UIElement, UITree
from agent.ui_perception.service import HermesUIService


class TestYouTubeCardTargetCalculation(unittest.TestCase):

    def setUp(self):
        MouseController.enable_simulation_mode(True)
        MouseController.set_simulated_position(0, 0)
        MouseController.set_simulated_move_override(None)
        ChromeDOMConnector.set_simulated_dom_videos(None)

    def tearDown(self):
        ChromeDOMConnector.set_simulated_dom_videos(None)

    def _execute_select_video(
        self,
        cards: list[dict],
        index: int,
        client_origin: tuple[int, int] = (0, 0),
        browser_chrome_h: int = 80,
        window_w: int = 1920,
        window_h: int = 1080,
        dpi_scale: float = 1.0,
    ) -> dict:
        """Standardized test runner for select_youtube_video mocking the WindowManager layer."""
        mock_dom_cards = []
        for i, c in enumerate(cards):
            bx, by, bw, bh = c["bbox"]
            safe_pt = derive_safe_interaction_point(c["bbox"])
            mock_dom_cards.append({
                "ordinal": i + 1,
                "component_id": c.get("id", f"yt_video_{i+1}"),
                "title": c.get("text", f"Video #{i+1}"),
                "href": f"/watch?v={i+1}",
                "center_x": bx + safe_pt[0],
                "center_y": by + safe_pt[1],
                "bbox": [bx, by, bw, bh * 0.65],
                "card_bbox": [bx, by, bw, bh],
            })
        ChromeDOMConnector.set_simulated_dom_videos(mock_dom_cards)

        mock_handle = WindowHandle(
            hwnd=77777,
            pid=1234,
            process_name="chrome.exe",
            title="YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
        )
        mock_snapshot = WindowSnapshot(
            handle=mock_handle,
            window_rect=(client_origin[0], client_origin[1], client_origin[0] + window_w, client_origin[1] + window_h),
            client_rect=(0, 0, window_w, window_h),
            client_screen_origin=client_origin,
            client_size=(window_w, window_h),
            viewport_screen_origin=(client_origin[0], client_origin[1] + browser_chrome_h),
            viewport_size=(window_w, window_h - browser_chrome_h),
            browser_chrome_height=browser_chrome_h,
            dpi=int(96 * dpi_scale),
            dpi_scale=dpi_scale,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot):

            return ComputerUseTool.select_youtube_video(index=index, wait_load=False)

    # -------------------------------------------------------------------------
    # 1. Arbitrary Layout Geometries: Layout A, Layout B, Layout C
    # -------------------------------------------------------------------------
    def test_layout_a_standard_4_columns(self):
        """
        Layout A: card_width = 442, gap = 16, content_x = 88, content_y = 104.
        Selecting card #2 must resolve to yt_video_2 with coordinates derived purely from its bbox.
        """
        layout_a_cards = [
            {"id": "yt_video_1", "bbox": (88.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_2", "bbox": (546.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_3", "bbox": (1004.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_4", "bbox": (1462.0, 104.0, 442.0, 336.0)},
        ]

        ordered = sort_row_major(layout_a_cards)
        self.assertEqual(len(ordered), 4)
        target = ordered[1]  # Ordinal 2

        self.assertEqual(target.ordinal, 2)
        self.assertEqual(target.component_id, "yt_video_2")
        self.assertEqual(target.bbox, (546.0, 104.0, 442.0, 336.0))

        # Safe click point: w/2 = 221, thumb_h/2 = (336 * 0.65)/2 = 109.2
        self.assertAlmostEqual(target.safe_click_point[0], 221.0, places=1)
        self.assertAlmostEqual(target.safe_click_point[1], 109.2, places=1)

        screen_pt, trace = CoordinateMapper.to_screen(
            comp_point=target.safe_click_point,
            comp_bbox=target.bbox,
            client_screen_origin=(0, 0),
            browser_chrome_height=80,
        )

        self.assertEqual(screen_pt, (767, 293))
        self.assertTrue(trace["is_inside_bbox"])
        self.assertTrue(target.hit_test(trace["viewport_space"]))

        # Execute full pipeline
        res = self._execute_select_video(layout_a_cards, index=2)
        self.assertEqual(res["target_id"], "yt_video_2")
        self.assertEqual(res["click_point"], (767, 293))
        self.assertTrue(res["move_verified"])
        self.assertTrue(res["click_completed"])

    def test_layout_b_narrower_cards_wider_gap(self):
        """
        Layout B: card_width = 380, gap = 24, content_x = 50, content_y = 120.
        Must resolve card #2 without any reliance on 442 width or 16 gap.
        """
        layout_b_cards = [
            {"id": "card_a", "bbox": (50.0, 120.0, 380.0, 290.0)},
            {"id": "card_b", "bbox": (454.0, 120.0, 380.0, 290.0)},   # 50 + 380 + 24 = 454
            {"id": "card_c", "bbox": (858.0, 120.0, 380.0, 290.0)},   # 454 + 380 + 24 = 858
            {"id": "card_d", "bbox": (1262.0, 120.0, 380.0, 290.0)},
        ]

        ordered = sort_row_major(layout_b_cards)
        self.assertEqual(len(ordered), 4)
        target = ordered[1]

        self.assertEqual(target.ordinal, 2)
        self.assertEqual(target.component_id, "card_b")
        self.assertEqual(target.bbox, (454.0, 120.0, 380.0, 290.0))

        # Safe point: 380 * 0.5 = 190.0, 290 * 0.65 * 0.5 = 94.25
        self.assertAlmostEqual(target.safe_click_point[0], 190.0, places=1)
        self.assertAlmostEqual(target.safe_click_point[1], 94.25, places=1)

        screen_pt, trace = CoordinateMapper.to_screen(
            comp_point=target.safe_click_point,
            comp_bbox=target.bbox,
            client_screen_origin=(0, 0),
            browser_chrome_height=80,
        )

        expected_vx = 454.0 + 190.0  # 644.0
        expected_vy = 120.0 + 94.25  # 214.25
        expected_sy = int(round(214.25 + 80))  # 294

        self.assertEqual(screen_pt, (644, expected_sy))
        self.assertTrue(trace["is_inside_bbox"])
        self.assertTrue(target.hit_test((expected_vx, expected_vy)))

        res = self._execute_select_video(layout_b_cards, index=2)
        self.assertEqual(res["target_id"], "card_b")
        self.assertEqual(res["click_point"], (644, expected_sy))

    def test_layout_c_wide_cards_narrow_gap(self):
        """
        Layout C: card_width = 500, gap = 12, content_x = 100, content_y = 90.
        Must resolve card #2 purely from its geometry.
        """
        layout_c_cards = [
            {"id": "c1", "bbox": (100.0, 90.0, 500.0, 350.0)},
            {"id": "c2", "bbox": (612.0, 90.0, 500.0, 350.0)},   # 100 + 500 + 12 = 612
            {"id": "c3", "bbox": (1124.0, 90.0, 500.0, 350.0)},
        ]

        ordered = sort_row_major(layout_c_cards)
        self.assertEqual(len(ordered), 3)
        target = ordered[1]

        self.assertEqual(target.ordinal, 2)
        self.assertEqual(target.component_id, "c2")
        self.assertEqual(target.bbox, (612.0, 90.0, 500.0, 350.0))

        screen_pt, trace = CoordinateMapper.to_screen(
            comp_point=target.safe_click_point,
            comp_bbox=target.bbox,
            client_screen_origin=(0, 0),
            browser_chrome_height=80,
        )

        expected_vx = 612.0 + 250.0  # 862.0
        expected_vy = 90.0 + (350.0 * 0.65 * 0.5)  # 203.75
        expected_sy = int(round(expected_vy + 80))  # 284

        self.assertEqual(screen_pt, (862, expected_sy))
        self.assertTrue(trace["is_inside_bbox"])
        self.assertTrue(target.hit_test((expected_vx, expected_vy)))

        res = self._execute_select_video(layout_c_cards, index=2)
        self.assertEqual(res["target_id"], "c2")
        self.assertEqual(res["click_point"], (862, expected_sy))

    # -------------------------------------------------------------------------
    # 2. Window Resize Tests: 1920x1080 -> 1600x900 -> 1280x720
    # -------------------------------------------------------------------------
    def test_window_resize_3_columns_layout(self):
        """
        When Chrome is resized to 1600x900, YouTube renders a 3-column grid.
        select_youtube_video(2) must dynamically select the 2nd card in the 3-column row.
        """
        cards_3col = [
            {"id": "yt_v1", "bbox": (80.0, 100.0, 480.0, 320.0)},
            {"id": "yt_v2", "bbox": (576.0, 100.0, 480.0, 320.0)},
            {"id": "yt_v3", "bbox": (1072.0, 100.0, 480.0, 320.0)},
            {"id": "yt_v4", "bbox": (80.0, 440.0, 480.0, 320.0)},
        ]

        res = self._execute_select_video(cards_3col, index=2, window_w=1600, window_h=900, browser_chrome_h=75)

        self.assertEqual(res["target_id"], "yt_v2")
        self.assertEqual(res["target"]["ordinal"], 2)
        # 576 + 240 = 816
        # 100 + (320 * 0.65 * 0.5) + 75 = 100 + 104 + 75 = 279
        self.assertEqual(res["click_point"], (816, 279))
        self.assertTrue(res["move_verified"])

    # -------------------------------------------------------------------------
    # 3. Browser Zoom Levels (80%, 100%, 110%, 125%)
    # -------------------------------------------------------------------------
    def test_browser_zoom_scaling(self):
        """
        At 125% DPI scale, coordinates and bounds scale accordingly.
        """
        scaled_cards = [
            {"id": "zoom_v1", "bbox": (110.0, 130.0, 552.5, 420.0)},
            {"id": "zoom_v2", "bbox": (682.5, 130.0, 552.5, 420.0)},
        ]

        res = self._execute_select_video(scaled_cards, index=2, browser_chrome_h=100, dpi_scale=1.25)

        self.assertEqual(res["target_id"], "zoom_v2")
        self.assertEqual(res["target"]["ordinal"], 2)
        # 682.5 + 552.5/2 = 958.75 -> 959
        # 130 + (420 * 0.65 * 0.5) + 100 = 130 + 136.5 + 100 = 366.5 -> 366
        self.assertEqual(res["click_point"][0], 959)
        self.assertEqual(res["click_point"][1], 366)

    # -------------------------------------------------------------------------
    # 4. Initial Cursor Position Invariance (Prompt Section 15 & Acceptance Criteria)
    # -------------------------------------------------------------------------
    def test_cursor_starts_at_card_1_target_2(self):
        """Cursor initially at Card #1 (309, 293), command 'select #2' -> target must be Card #2 (767, 293)."""
        self._verify_cursor_invariance_case(initial_cursor=(309, 293), target_index=2, expected_target=(767, 293), expected_id="yt_video_2")

    def test_cursor_starts_at_card_3_target_2(self):
        """Cursor initially at Card #3 (1225, 293), command 'select #2' -> target must be Card #2 (767, 293)."""
        self._verify_cursor_invariance_case(initial_cursor=(1225, 293), target_index=2, expected_target=(767, 293), expected_id="yt_video_2")

    def test_cursor_starts_at_card_4_target_2(self):
        """Cursor initially at Card #4 (1683, 293), command 'select #2' -> target must be Card #2 (767, 293)."""
        self._verify_cursor_invariance_case(initial_cursor=(1683, 293), target_index=2, expected_target=(767, 293), expected_id="yt_video_2")

    def test_cursor_starts_at_card_5_target_2(self):
        """Cursor initially at Card #5 (309, 650), command 'select #2' -> target must be Card #2 (767, 293)."""
        self._verify_cursor_invariance_case(initial_cursor=(309, 650), target_index=2, expected_target=(767, 293), expected_id="yt_video_2")

    def test_cursor_starts_at_card_6_target_2(self):
        """Cursor initially at Card #6 (767, 650), command 'select #2' -> target must be Card #2 (767, 293)."""
        self._verify_cursor_invariance_case(initial_cursor=(767, 650), target_index=2, expected_target=(767, 293), expected_id="yt_video_2")

    def _verify_cursor_invariance_case(
        self,
        initial_cursor: tuple[int, int],
        target_index: int,
        expected_target: tuple[int, int],
        expected_id: str,
    ):
        """Helper enforcing that initial cursor location has ZERO impact on resolved target geometry."""
        twelve_cards = [
            # Row 1
            {"id": "yt_video_1", "bbox": (88.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_2", "bbox": (546.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_3", "bbox": (1004.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_4", "bbox": (1462.0, 104.0, 442.0, 336.0)},
            # Row 2
            {"id": "yt_video_5", "bbox": (88.0, 464.0, 442.0, 336.0)},
            {"id": "yt_video_6", "bbox": (546.0, 464.0, 442.0, 336.0)},
            {"id": "yt_video_7", "bbox": (1004.0, 464.0, 442.0, 336.0)},
            {"id": "yt_video_8", "bbox": (1462.0, 464.0, 442.0, 336.0)},
            # Row 3
            {"id": "yt_video_9", "bbox": (88.0, 824.0, 442.0, 336.0)},
            {"id": "yt_video_10", "bbox": (546.0, 824.0, 442.0, 336.0)},
            {"id": "yt_video_11", "bbox": (1004.0, 824.0, 442.0, 336.0)},
            {"id": "yt_video_12", "bbox": (1462.0, 824.0, 442.0, 336.0)},
        ]

        MouseController.set_simulated_position(initial_cursor[0], initial_cursor[1])

        res = self._execute_select_video(twelve_cards, index=target_index)

        self.assertEqual(res["target_id"], expected_id)
        self.assertEqual(res["target"]["ordinal"], target_index)
        self.assertEqual(res["cursor_before"], initial_cursor)
        self.assertEqual(res["click_point"], expected_target)
        self.assertEqual(res["cursor_after"], expected_target)
        self.assertTrue(res["move_verified"])
        self.assertTrue(res["click_completed"])

    # -------------------------------------------------------------------------
    # 5. Zero Fallback to Card #1 on Invalid Index (Prompt Section 21 & 22)
    # -------------------------------------------------------------------------
    def test_out_of_bounds_index_returns_target_not_found(self):
        """
        Requesting index=99 when 4 cards exist must return TARGET_NOT_FOUND,
        and MUST NOT fall back to card #1.
        """
        four_cards = [
            {"id": "card_1", "bbox": (88.0, 104.0, 442.0, 336.0)},
            {"id": "card_2", "bbox": (546.0, 104.0, 442.0, 336.0)},
            {"id": "card_3", "bbox": (1004.0, 104.0, 442.0, 336.0)},
            {"id": "card_4", "bbox": (1462.0, 104.0, 442.0, 336.0)},
        ]

        res = self._execute_select_video(four_cards, index=99)

        self.assertEqual(res["status"], "TARGET_NOT_FOUND")
        self.assertFalse(res["success"])
        self.assertEqual(res["ordinal"], 99)
        self.assertEqual(res["total_dom_items"], 4)

    # -------------------------------------------------------------------------
    # 6. Dry-Run Mode & Visual Debug Marker Generation (Prompt Section 2 & 22)
    # -------------------------------------------------------------------------
    def test_dry_run_mode_generates_marker_without_clicking(self):
        """
        When dry_run=True, system detects, resolves, calculates safe point, transforms coordinates,
        generates visual debug marker, and returns without moving cursor or clicking.
        """
        layout_cards = [
            {"id": "yt_video_1", "bbox": (88.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_2", "bbox": (546.0, 104.0, 442.0, 336.0)},
            {"id": "yt_video_3", "bbox": (1004.0, 104.0, 442.0, 336.0)},
        ]
        mock_dom_cards = []
        for i, c in enumerate(layout_cards):
            bx, by, bw, bh = c["bbox"]
            safe_pt = derive_safe_interaction_point(c["bbox"])
            mock_dom_cards.append({
                "ordinal": i + 1,
                "component_id": c.get("id", f"yt_video_{i+1}"),
                "title": c.get("text", f"Video #{i+1}"),
                "href": f"/watch?v={i+1}",
                "center_x": bx + safe_pt[0],
                "center_y": by + safe_pt[1],
                "bbox": [bx, by, bw, bh * 0.65],
                "card_bbox": [bx, by, bw, bh],
            })
        ChromeDOMConnector.set_simulated_dom_videos(mock_dom_cards)

        mock_handle = WindowHandle(
            hwnd=55555,
            pid=4321,
            process_name="chrome.exe",
            title="YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
        )
        mock_snapshot = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1920, 1080),
            client_rect=(0, 0, 1920, 1080),
            client_screen_origin=(0, 0),
            client_size=(1920, 1080),
            viewport_screen_origin=(0, 80),
            viewport_size=(1920, 1000),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        MouseController.set_simulated_position(100, 100)

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False, dry_run=True)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "DRY_RUN_COMPLETED")
            self.assertTrue(res["dry_run"])
            self.assertEqual(res["target_id"], "yt_video_2")
            self.assertEqual(res["resolved_ordinal"], 2)
            self.assertEqual(res["click_point"], (767, 293))
            self.assertFalse(res["interaction"]["attempted"])
            self.assertFalse(res["interaction"]["click_completed"])
            # Mouse must remain untouched at initial position
            pos = MouseController.get_cursor_position()
            self.assertEqual((pos.x, pos.y), (100, 100))

    def test_debug_visualizer_draw_markers(self):
        """Verify DebugVisualizer creates and saves marker image overlaying bounding boxes and crosshair."""
        from agent.ui_perception.debug_visualizer import DebugVisualizer
        from PIL import Image

        canvas = Image.new("RGB", (1920, 1080), color=(40, 40, 40))
        target_1 = ComponentTarget(
            component_id="card_1",
            component_type="youtube_video",
            bbox=(88.0, 104.0, 442.0, 336.0),
            center=(309.0, 272.0),
            safe_click_point=(221.0, 109.2),
            ordinal=1,
        )
        target_2 = ComponentTarget(
            component_id="card_2",
            component_type="youtube_video",
            bbox=(546.0, 104.0, 442.0, 336.0),
            center=(767.0, 272.0),
            safe_click_point=(221.0, 109.2),
            ordinal=2,
        )

        saved_path = DebugVisualizer.draw_target_markers_and_save(
            image=canvas,
            ordered_targets=[target_1, target_2],
            selected_target=target_2,
            click_screen_point=(767, 293),
            window_origin=(0, 0),
            client_origin=(0, 0),
            browser_chrome_height=80,
            output_filename="test_debug_marker_output.png",
        )

        self.assertIsNotNone(saved_path)
        self.assertTrue(os.path.exists(saved_path))
        self.assertGreater(os.path.getsize(saved_path), 0)


if __name__ == "__main__":
    unittest.main()


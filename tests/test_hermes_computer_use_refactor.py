"""
Comprehensive Unit & Regression Test Suite for Refactored Hermes Computer-Use Tools:
1. Window Targeting & Read-Only Validation (Zero ShowWindow recovery loops, minimal activation)
2. Single-Source-of-Truth Coordinate Transformation (Component -> Viewport -> Client -> Screen)
3. Component Target & Row-Major Ordinal Sorting (Top -> Bottom, Left -> Right)
4. Safe Interaction Point derivation (avoid avatars, duration badge, menus)
5. Exactly-Once Physical Input Execution (click_count == 1, ZERO business retries)
6. UI Interaction Service Transaction Pipeline & State Reporting
7. Voice Memory Normalization (No recursive 'click click click...' string mutation)
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.browser_context import WindowHandle, WindowSnapshot
from agent.tools.component_target import (
    ComponentTarget,
    derive_safe_interaction_point,
    sort_row_major,
)
from agent.tools.coordinate_mapper import CoordinateMapper, CoordinateSpace
from agent.tools.interaction_executor import InteractionExecutor
from agent.tools.ui_interaction_service import UIInteractionService
from agent.tools.window_manager import WindowManager
from agent.voice_memory import VoiceMemory


class TestHermesComputerUseRefactor(unittest.TestCase):
    """
    Test suite for the new Hermes Computer-Use architecture.
    """

    def setUp(self):
        InteractionExecutor.set_simulation_mode(True)

    def tearDown(self):
        InteractionExecutor.set_simulation_mode(False)

    # -------------------------------------------------------------------------
    # 1. Window Manager & Minimal Activation Tests
    # -------------------------------------------------------------------------
    def test_window_activation_minimal_when_already_foreground(self):
        """If target window is already foreground, activation must be a NO-OP."""
        handle = WindowHandle(hwnd=1001, pid=5000, process_name="chrome.exe", title="YouTube", class_name="Chrome_WidgetWin_1")

        with patch("agent.tools.window_manager.user32") as mock_u32:
            mock_u32.GetForegroundWindow.return_value = 1001
            # Should return True immediately without calling SetForegroundWindow or keybd_event
            activated = WindowManager.activate_window(handle)
            self.assertTrue(activated)
            self.assertFalse(mock_u32.SetForegroundWindow.called)

    def test_window_validation_is_strictly_read_only(self):
        """Validation must verify state without calling ShowWindow or modifying window."""
        handle = WindowHandle(hwnd=2002, pid=6000, process_name="chrome.exe", title="Google Chrome", class_name="Chrome_WidgetWin_1")

        with patch("agent.tools.window_manager.user32") as mock_u32:
            mock_u32.IsWindow.return_value = True
            mock_u32.IsWindowVisible.return_value = True
            mock_u32.IsIconic.return_value = False

            def get_rect(hwnd, byref_rect):
                r = byref_rect._obj if hasattr(byref_rect, "_obj") else byref_rect
                r.left = 0
                r.top = 0
                r.right = 1920
                r.bottom = 1080
                return 1

            mock_u32.GetWindowRect.side_effect = get_rect

            is_valid, reason = WindowManager.validate_window(handle, check_minimized=True)
            self.assertTrue(is_valid)
            self.assertEqual(reason, "VALID")
            # ShowWindow must NEVER be called during validation!
            self.assertFalse(mock_u32.ShowWindow.called)

    # -------------------------------------------------------------------------
    # 2. Single-Source-of-Truth Coordinate Transformation Tests
    # -------------------------------------------------------------------------
    def test_coordinate_mapper_pipeline(self):
        """Test exact mathematical mapping: Component -> Viewport -> Client -> Screen."""
        comp_point = (160.0, 90.0)
        comp_bbox = (40.0, 100.0, 320.0, 180.0)
        client_origin = (100, 50)
        chrome_h = 80

        screen_pt, trace = CoordinateMapper.to_screen(
            comp_point=comp_point,
            comp_bbox=comp_bbox,
            client_screen_origin=client_origin,
            browser_chrome_height=chrome_h,
        )

        # Expected:
        # Viewport: (40 + 160, 100 + 90) = (200, 190)
        # Client:   (200, 190 + 80) = (200, 270)
        # Screen:   (100 + 200, 50 + 270) = (300, 320)
        self.assertEqual(screen_pt, (300, 320))
        self.assertEqual(trace["component_space"], (160.0, 90.0))
        self.assertEqual(trace["viewport_space"], (200.0, 190.0))
        self.assertEqual(trace["window_client_space"], (200.0, 270.0))
        self.assertEqual(trace["screen_space"], (300, 320))

    # -------------------------------------------------------------------------
    # 3. Component Target & Row-Major Ordinal Sorting Tests
    # -------------------------------------------------------------------------
    def test_row_major_ordinal_sorting_grid(self):
        """
        Verify that components returned in arbitrary detector order are deterministically
        sorted row-major (top-to-bottom, left-to-right).
        """
        # 2x2 grid created in mixed detector order
        raw_items = [
            {"id": "c4_bottom_right", "bbox": (400, 300, 300, 200)},
            {"id": "c1_top_left",     "bbox": (50,  50,  300, 200)},
            {"id": "c3_bottom_left",  "bbox": (50,  300, 300, 200)},
            {"id": "c2_top_right",    "bbox": (400, 50,  300, 200)},
        ]

        ordered = sort_row_major(raw_items, y_tolerance_ratio=0.4)
        self.assertEqual(len(ordered), 4)
        self.assertEqual(ordered[0].component_id, "c1_top_left")
        self.assertEqual(ordered[1].component_id, "c2_top_right")
        self.assertEqual(ordered[2].component_id, "c3_bottom_left")
        self.assertEqual(ordered[3].component_id, "c4_bottom_right")
        self.assertEqual(ordered[0].ordinal, 1)
        self.assertEqual(ordered[1].ordinal, 2)
        self.assertEqual(ordered[2].ordinal, 3)
        self.assertEqual(ordered[3].ordinal, 4)

    def test_derive_safe_interaction_point_avoids_edges(self):
        """Thumbnail center must be selected while avoiding avatar/duration overlay areas."""
        bbox = (0.0, 0.0, 360.0, 280.0)  # Video card
        safe_pt = derive_safe_interaction_point(bbox, "youtube_video")

        # Thumbnail center is at 50% X and (65% * 50%) Y (upper region of card)
        self.assertAlmostEqual(safe_pt[0], 180.0)
        self.assertAlmostEqual(safe_pt[1], 91.0)

    # -------------------------------------------------------------------------
    # 4. Exactly-Once Physical Input Execution Tests
    # -------------------------------------------------------------------------
    def test_interaction_executor_dispatches_once_without_retries(self):
        """InteractionExecutor must execute exactly one physical click action."""
        InteractionExecutor.set_simulated_cursor(100, 100)
        res = InteractionExecutor.click((500, 300), click_count=1)

        self.assertTrue(res["success"])
        self.assertTrue(res["click_completed"])
        self.assertEqual(res["target"], (500, 300))
        self.assertEqual(res["cursor_after"], (500, 300))

    # -------------------------------------------------------------------------
    # 5. UI Interaction Service Pipeline & State Reporting Tests
    # -------------------------------------------------------------------------
    def test_ui_interaction_service_clicked_but_unverified_state(self):
        """
        When click completes physically but video transition is unverified,
        the service must return status CLICKED_BUT_UNVERIFIED without retrying.
        """
        mock_handle = WindowHandle(hwnd=8888, pid=1234, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
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

        mock_components = [
            {"id": "yt_video_1", "bbox": (50, 50, 360, 280)},
            {"id": "yt_video_2", "bbox": (450, 50, 360, 280)},
        ]

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=mock_components), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(False, "Title not updated")):

            res = UIInteractionService.select_youtube_video(index=2, wait_load=False)

            self.assertEqual(res["status"], "CLICKED_BUT_UNVERIFIED")
            self.assertTrue(res["interaction"]["click_completed"])
            self.assertFalse(res["verification"]["verified"])
            self.assertTrue(res["mouse_action_success"])
            self.assertFalse(res["target_interaction_verified"])
            self.assertIn("playback could not be confirmed", res["message"])

    def test_ui_interaction_service_success_state(self):
        """When click succeeds and transition is verified, status must be SUCCESS."""
        mock_handle = WindowHandle(hwnd=8888, pid=1234, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
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

        mock_components = [
            {"id": "yt_video_1", "bbox": (50, 50, 360, 280)},
            {"id": "yt_video_2", "bbox": (450, 50, 360, 280)},
        ]

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=mock_components), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(True, "Title changed to Watch")):

            res = UIInteractionService.select_youtube_video(index=2, wait_load=False)

            self.assertEqual(res["status"], "SUCCESS")
            self.assertTrue(res["success"])
            self.assertTrue(res["interaction"]["click_completed"])
            self.assertTrue(res["verification"]["verified"])
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["target_interaction_verified"])
            self.assertIn("Clicked and played YouTube video 2", res["message"])

    # -------------------------------------------------------------------------
    # 6. Voice Memory Normalization Non-Recursive String Safety Tests
    # -------------------------------------------------------------------------
    def test_voice_memory_prevents_click_click_corruption(self):
        """
        Spoken queries like 'Play the second video' or 'Chọn video thứ 2'
        must NOT mutate recursively into 'click click click second video'.
        """
        vm = VoiceMemory.get_instance()

        phrases = [
            "Play the second video",
            "play second video",
            "les second videos",
            "chon video thu 2",
            "play the first video",
            "Play the third video",
        ]

        for p in phrases:
            norm, _ = vm.normalize(p)
            self.assertNotIn("click click", norm, f"Corrupted phrase generated: {norm} from {p}")
            self.assertNotIn("click click click", norm)


if __name__ == "__main__":
    unittest.main()

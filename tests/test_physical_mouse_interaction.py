"""
Comprehensive Unit & Regression Test Suite for Physical Mouse Interaction & Move Verification.
Covers:
1. Reproduction of exact bug: move fails (stuck at (631,501) instead of target (767,293)) -> MUST ABORT, NO CLICK
2. Success case: move succeeds to (767,293) -> physical click dispatched exactly once
3. Click count invariant: click_count == 1 even if post-click transition fails
4. Target ordinals #1, #2, #3: verification of exact physical coordinate per card
5. Distinct #1 vs #2 regression: cursor at #1 (309,272), command target #2 -> must reach #2 or abort
6. Thread-safe mutex serialization
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.browser_context import WindowHandle, WindowSnapshot
from agent.tools.component_target import ComponentTarget
from agent.tools.interaction_executor import InteractionExecutor
from agent.tools.mouse_backend import SimulationBackend
from agent.tools.mouse_controller import ClickResult, MouseController, MoveResult
from agent.tools.ui_interaction_service import UIInteractionService
from agent.tools.window_manager import WindowManager


class TestPhysicalMouseInteraction(unittest.TestCase):
    """
    Test suite enforcing deterministic physical mouse verification and execution invariants.
    """

    def setUp(self):
        MouseController.enable_simulation_mode(True)
        MouseController.set_simulated_move_override(None)
        MouseController.set_simulated_position(0, 0)

    def tearDown(self):
        MouseController.set_simulated_move_override(None)
        MouseController.enable_simulation_mode(False)

    # -------------------------------------------------------------------------
    # 1. Exact Bug Reproduction Test (Prompt Section 20)
    # -------------------------------------------------------------------------
    def test_reproduction_cursor_stuck_aborts_click(self):
        """
        REPRODUCTION TEST:
        Initial cursor: (631, 501)
        Requested target: (767, 293)
        Actual cursor after move: (631, 501) (movement failed / restricted)

        EXPECTED:
        - move_verified = False
        - click_dispatched = False
        - click_completed = False
        - status = "MOVE_FAILED"
        - NO physical click dispatched!
        """
        # Set initial cursor to (631, 501)
        MouseController.set_simulated_position(631, 501)
        # Override simulated move so cursor remains stuck at (631, 501)
        MouseController.set_simulated_move_override((631, 501))

        with patch.object(MouseController, "_click_current_position") as mock_click:
            res = InteractionExecutor.click((767, 293), click_count=1)

            # Click MUST NOT be called!
            self.assertFalse(mock_click.called, "Click must NEVER be dispatched when move fails!")

            self.assertFalse(res["success"])
            self.assertFalse(res["move_verified"])
            self.assertFalse(res["click_dispatched"])
            self.assertFalse(res["click_completed"])
            self.assertEqual(res["status"], "MOVE_FAILED")
            self.assertEqual(res["target"], (767, 293))
            self.assertEqual(res["actual_position_before"], (631, 501))
            self.assertEqual(res["actual_position_after_move"], (631, 501))
            self.assertIn("failed", res["error"].lower())

    # -------------------------------------------------------------------------
    # 2. Success Case Test (Prompt Section 21)
    # -------------------------------------------------------------------------
    def test_move_succeeds_dispatches_verified_click(self):
        """
        SUCCESS TEST:
        Initial cursor: (631, 501)
        Requested target: (767, 293)
        Actual cursor after move: (767, 293)

        EXPECTED:
        - move_verified = True
        - click_dispatched = True
        - click_completed = True
        - actual_position_at_click = (767, 293)
        """
        MouseController.set_simulated_position(631, 501)
        MouseController.set_simulated_move_override(None)  # Normal movement to target

        res = InteractionExecutor.click((767, 293), click_count=1)

        self.assertTrue(res["success"])
        self.assertTrue(res["move_verified"])
        self.assertTrue(res["click_dispatched"])
        self.assertTrue(res["click_completed"])
        self.assertEqual(res["target"], (767, 293))
        self.assertEqual(res["actual_position_before"], (631, 501))
        self.assertEqual(res["actual_position_at_click"], (767, 293))

    # -------------------------------------------------------------------------
    # 3. Click Count Invariant (Prompt Section 22)
    # -------------------------------------------------------------------------
    def test_click_count_invariant_zero_retries(self):
        """
        Verify click_count == 1 even if post-click verification fails.
        No business retries allowed.
        """
        mock_handle = WindowHandle(hwnd=9999, pid=1234, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
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
            {"id": "yt_video_1", "bbox": (88, 104, 442, 336)},
            {"id": "yt_video_2", "bbox": (546, 104, 442, 336)},
            {"id": "yt_video_3", "bbox": (1004, 104, 442, 336)},
        ]

        dispatch_count = 0

        def count_click(*args, **kwargs):
            nonlocal dispatch_count
            dispatch_count += 1
            return ClickResult(
                success=True,
                click_completed=True,
                mouse_action_success=True,
                click_dispatched=True,
                position_at_click=(767, 293),
                button="left",
                click_count=1,
                down_success=True,
                up_success=True,
                status="CLICK_DISPATCHED",
            )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=mock_components), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(False, "Page did not transition")), \
             patch.object(MouseController, "_click_current_position", side_effect=count_click):

            res = UIInteractionService.select_youtube_video(index=2, wait_load=False)

            self.assertEqual(dispatch_count, 1, "Exactly one click dispatch must occur!")
            self.assertEqual(res["status"], "CLICKED_BUT_UNVERIFIED")
            self.assertTrue(res["interaction"]["click_completed"])
            self.assertFalse(res["verification"]["verified"])
            self.assertFalse(res["window_recovered"])

    # -------------------------------------------------------------------------
    # 4. Target Ordinals #1 / #2 / #3 Coordinates (Prompt Section 23)
    # -------------------------------------------------------------------------
    def test_target_ordinals_1_2_3_coordinates(self):
        """
        Verify that video #1, #2, and #3 map to distinct valid screen coordinates
        and physical cursor is verified at each coordinate before click.
        """
        mock_handle = WindowHandle(hwnd=9999, pid=1234, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
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
            {"id": "yt_video_1", "bbox": (88, 104, 442, 336)},
            {"id": "yt_video_2", "bbox": (546, 104, 442, 336)},
            {"id": "yt_video_3", "bbox": (1004, 104, 442, 336)},
        ]

        # Expected centers:
        # #1: X = 88 + 221 = 309, Y = 104 + (336 * 0.65 * 0.5) + 80 = 104 + 109.2 + 80 = 293.2 -> 293
        # #2: X = 546 + 221 = 767, Y = 293
        # #3: X = 1004 + 221 = 1225, Y = 293

        for idx, exp_x in [(1, 309), (2, 767), (3, 1225)]:
            with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
                 patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
                 patch.object(WindowManager, "activate_window", return_value=True), \
                 patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot), \
                 patch.object(UIInteractionService, "_perceive_video_components", return_value=mock_components), \
                 patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(True, "Transition verified")):

                res = UIInteractionService.select_youtube_video(index=idx, wait_load=False)
                self.assertTrue(res["success"])
                self.assertEqual(res["target"]["screen_point"][0], exp_x)
                self.assertEqual(res["actual_position_at_click"][0], exp_x)
                self.assertTrue(res["move_verified"])

    # -------------------------------------------------------------------------
    # 5. Distinct #1 vs #2 Regression Test (Prompt Section 24)
    # -------------------------------------------------------------------------
    def test_distinct_target_1_and_2_aborts_if_cursor_stuck_at_1(self):
        """
        Cursor is initially at card #1 (309, 293).
        Command targets card #2 (767, 293).
        If physical move fails and cursor remains at card #1 -> ABORT! Never click card #1!
        """
        # Initial cursor at card #1
        MouseController.set_simulated_position(309, 293)
        # Movement failure keeps cursor at card #1
        MouseController.set_simulated_move_override((309, 293))

        mock_handle = WindowHandle(hwnd=9999, pid=1234, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
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
            {"id": "yt_video_1", "bbox": (88, 104, 442, 336)},
            {"id": "yt_video_2", "bbox": (546, 104, 442, 336)},
        ]

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TEST")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=mock_components), \
             patch.object(MouseController, "_click_current_position") as mock_click:

            res = UIInteractionService.select_youtube_video(index=2, wait_load=False)

            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "MOVE_FAILED")
            self.assertFalse(res["move_verified"])
            self.assertFalse(res["click_completed"])
            self.assertFalse(mock_click.called, "Click must NOT be executed on card #1 when card #2 was requested!")

    # -------------------------------------------------------------------------
    # 6. Thread-Safe Mutex Serialization Test (Prompt Section 28)
    # -------------------------------------------------------------------------
    def test_mouse_mutex_serialization(self):
        """
        Verify that concurrent threads accessing MouseController are properly serialized
        without race conditions.
        """
        results = []

        def worker(target_x, target_y):
            res = MouseController.move_to((target_x, target_y))
            results.append(res.verified)

        threads = [
            threading.Thread(target=worker, args=(100 * i, 100 * i))
            for i in range(1, 6)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)
        self.assertTrue(all(results))


if __name__ == "__main__":
    unittest.main()

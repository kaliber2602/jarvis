"""
Comprehensive Test Suite for Pre-Click Deterministic Targeting & YouTube Video Selection.
Verifies all 6 Acceptance Cases and Section 1-15 Requirements:
  - Case 1: Video 2 selection on 4-card grid (x=309, x=767, x=1225, x=1683) -> #2 target, point ≈ (767, 293), click_count=1
  - Case 2: Video 3 selection on 4-card grid -> #3 target, point ≈ (1225, 293), click_count=1
  - Case 3: Target uncertainty / invalid preconditions -> DO NOT CLICK (INVALID_TARGET_BEFORE_CLICK / TARGET_NOT_FOUND)
  - Case 4: Cursor movement fails / drifts -> DO NOT CLICK (MOVE_FAILED), no retry
  - Case 5: Stale UI snapshot before click -> DO NOT CLICK (SNAPSHOT_STALE)
  - Case 6: Post-click UI changes / delays -> CLICK_ONCE, ACTION_COMPLETED, no retry
  - Case 7: All 12 pre-click preconditions in TargetPreconditionValidator
  - Case 8: SafeClickRegion bounding & badge/menu exclusion
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.tools.browser_context import WindowHandle, WindowSnapshot
from agent.tools.component_target import (
    ComponentTarget,
    YouTubeVideoTarget,
    build_safe_click_region,
    resolve_safe_click_point,
    sort_row_major,
)
from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.tools.coordinate_mapper import CoordinateMapper
from agent.tools.interaction_executor import InteractionExecutor
from agent.tools.mouse_controller import MouseController
from agent.tools.ui_interaction_service import TaskWindowContext, UIInteractionService, YouTubeState
from agent.tools.window_manager import WindowIdentity, WindowInfo, WindowManager
from agent.ui_perception.models import (
    BoundingBox,
    ElementType,
    Point,
    PreconditionValidationResult,
    ResolutionStatus,
    SafeClickRegion,
    UIElement,
    UISnapshot,
    UITree,
    VisibilityState,
)
from agent.ui_perception.precondition_validator import TargetPreconditionValidator
from agent.ui_perception.service import HermesUIService


class TestPreClickDeterministicTargeting(unittest.TestCase):

    def setUp(self):
        MouseExecutor.set_simulation_mode(True)
        MouseExecutor.set_simulated_cursor(0, 0)
        MouseExecutor.set_simulated_move_override(None)

    def tearDown(self):
        MouseExecutor.set_simulated_move_override(None)

    # -------------------------------------------------------------------------
    # ACCEPTANCE CASE 1: Video 2 Selection on 4-Card Row
    # (x=309, x=767, x=1225, x=1683) -> #2 target, click point ≈ (767, 293), click_count = 1
    # -------------------------------------------------------------------------
    def test_acceptance_case_1_video_2_selection(self):
        # 4 cards on screen with x coordinates 309, 767, 1225, 1683 (width 442, height 336, y=104)
        # In a 1920x1080 screen with client_origin=(0, 0) and chrome_h=80:
        # Card 2 center x = 767. Safe thumbnail height = 336 * 0.65 = 218.4 (midpoint y = 109.2)
        # Screen Y = 80 (chrome) + 104 (content_y) + 109.2 ≈ 293.2 -> 293
        raw_components = [
            {"id": "yt_video_card_4", "bbox": (1462.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
            {"id": "yt_video_card_2", "bbox": (546.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
            {"id": "yt_video_card_1", "bbox": (88.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
            {"id": "yt_video_card_3", "bbox": (1004.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
        ]
        # Notice card centers:
        # Card 1: 88 + 221 = 309
        # Card 2: 546 + 221 = 767
        # Card 3: 1004 + 221 = 1225
        # Card 4: 1462 + 221 = 1683

        fake_handle = WindowHandle(hwnd=1001, pid=2001, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        fake_snapshot = WindowSnapshot(
            handle=fake_handle,
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

        with patch.object(WindowManager, "resolve_task_window", return_value=(fake_handle, "active")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "valid")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=fake_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=raw_components), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(True, "Title updated", YouTubeState(hwnd=1001, title="Video 2 - YouTube", page_type="WATCH_PAGE"))):

            res = UIInteractionService.select_youtube_video(index=2, application="chrome", wait_load=False)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["target"]["ordinal"], 2)
            self.assertEqual(res["target"]["component_id"], "yt_video_card_2")
            self.assertEqual(res["target"]["screen_point"], (767, 293))
            self.assertEqual(res["interaction"]["physical_click_count"], 1)
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["verification"]["overall"])

    # -------------------------------------------------------------------------
    # ACCEPTANCE CASE 2: Video 3 Selection on 4-Card Row
    # -> #3 target, click point ≈ (1225, 293), click_count = 1
    # -------------------------------------------------------------------------
    def test_acceptance_case_2_video_3_selection(self):
        raw_components = [
            {"id": "yt_video_card_4", "bbox": (1462.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
            {"id": "yt_video_card_1", "bbox": (88.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
            {"id": "yt_video_card_3", "bbox": (1004.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
            {"id": "yt_video_card_2", "bbox": (546.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
        ]

        fake_handle = WindowHandle(hwnd=1001, pid=2001, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        fake_snapshot = WindowSnapshot(
            handle=fake_handle,
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

        with patch.object(WindowManager, "resolve_task_window", return_value=(fake_handle, "active")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "valid")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=fake_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=raw_components), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(True, "Title updated", YouTubeState(hwnd=1001, title="Video 3 - YouTube", page_type="WATCH_PAGE"))):

            res = UIInteractionService.select_youtube_video(index=3, application="chrome", wait_load=False)

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["target"]["ordinal"], 3)
            self.assertEqual(res["target"]["component_id"], "yt_video_card_3")
            self.assertEqual(res["target"]["screen_point"], (1225, 293))
            self.assertEqual(res["interaction"]["physical_click_count"], 1)

    # -------------------------------------------------------------------------
    # ACCEPTANCE CASE 3: Target Uncertainty / Offscreen / Invalid Preconditions
    # -> DO NOT CLICK. No click event dispatched.
    # -------------------------------------------------------------------------
    def test_acceptance_case_3_uncertain_or_offscreen_target_aborts_before_click(self):
        # Card with 0 width/height
        raw_components = [
            {"id": "invalid_card", "bbox": (88.0, 104.0, 0.0, 0.0), "type": "VIDEO_CARD"},
        ]

        fake_handle = WindowHandle(hwnd=1001, pid=2001, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        fake_snapshot = WindowSnapshot(
            handle=fake_handle,
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

        with patch.object(WindowManager, "resolve_task_window", return_value=(fake_handle, "active")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "valid")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=fake_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=raw_components), \
             patch.object(MouseExecutor, "click_physical_point") as mock_click:

            res = UIInteractionService.select_youtube_video(index=1, application="chrome", wait_load=False)

            self.assertFalse(res["success"])
            self.assertFalse(res["interaction"]["click_dispatched"])
            mock_click.assert_not_called()

    # -------------------------------------------------------------------------
    # ACCEPTANCE CASE 4: Cursor Movement Fails / Drifts Beyond Tolerance
    # -> DO NOT CLICK. Abort before click, zero clicks dispatched.
    # -------------------------------------------------------------------------
    def test_acceptance_case_4_cursor_movement_failure_aborts_before_click(self):
        raw_components = [
            {"id": "card_1", "bbox": (88.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
        ]

        fake_handle = WindowHandle(hwnd=1001, pid=2001, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        fake_snapshot = WindowSnapshot(
            handle=fake_handle,
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

        # Force simulated mouse cursor to drift to (999, 999) instead of target (309, 293)
        MouseExecutor.set_simulated_move_override((999, 999))

        with patch.object(WindowManager, "resolve_task_window", return_value=(fake_handle, "active")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "valid")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=fake_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=raw_components), \
             patch.object(MouseController, "left_click") as mock_left_click:

            res = UIInteractionService.select_youtube_video(index=1, application="chrome", wait_load=False)

            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "MOVE_FAILED")
            self.assertFalse(res["interaction"]["click_dispatched"])
            mock_left_click.assert_not_called()

    # -------------------------------------------------------------------------
    # ACCEPTANCE CASE 5: Stale UI Snapshot / Window Context Change
    # -> Precondition validator fails with SNAPSHOT_STALE / INVALID_TARGET_BEFORE_CLICK -> DO NOT CLICK
    # -------------------------------------------------------------------------
    def test_acceptance_case_5_stale_snapshot_aborts_before_click(self):
        # Target element tested against a snapshot that is 10 seconds old
        stale_snapshot = UISnapshot(
            snapshot_id="SNAP-OLD",
            window_hwnd=1001,
            process_id=2001,
            process_name="chrome.exe",
            window_title="YouTube",
            page_type="HOME",
            timestamp=time.time() - 10.0,  # 10s old
            viewport_size=(1920, 1080),
        )

        elem = UIElement(
            id="yt_video_card_1",
            type=ElementType.VIDEO_CARD,
            bbox=BoundingBox(88, 104, 442, 336),
        )

        val_res = TargetPreconditionValidator.validate_preconditions(
            target_element=elem,
            snapshot=stale_snapshot,
            local_click_point=(221, 109),
            screen_click_point=(309, 293),
            max_snapshot_age_seconds=3.0,
        )

        self.assertFalse(val_res.valid)
        self.assertIn("snapshot_not_stale", val_res.failed_preconditions)
        self.assertEqual(val_res.status, ResolutionStatus.SNAPSHOT_STALE)

    # -------------------------------------------------------------------------
    # ACCEPTANCE CASE 6: UI Changes / Delayed Navigation Post-Click
    # -> CLICK_ONCE completes successfully without retry, passive observation records new state.
    # -------------------------------------------------------------------------
    def test_acceptance_case_6_post_click_navigation_delay_does_not_retry_or_fail(self):
        raw_components = [
            {"id": "yt_video_card_1", "bbox": (88.0, 104.0, 442.0, 336.0), "type": "VIDEO_CARD"},
        ]

        fake_handle = WindowHandle(hwnd=1001, pid=2001, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        fake_snapshot = WindowSnapshot(
            handle=fake_handle,
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

        # Mock transition observation returning unverified (e.g. slow network navigation)
        with patch.object(WindowManager, "resolve_task_window", return_value=(fake_handle, "active")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "valid")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=fake_snapshot), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=raw_components), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(False, "Transition still in progress", YouTubeState(hwnd=1001, title="YouTube - Google Chrome", page_type="HOME"))):

            res = UIInteractionService.select_youtube_video(index=1, application="chrome", wait_load=False)

            # Invariant: Click succeeded physically, click_count == 1, no retries
            self.assertEqual(res["status"], "CLICKED_BUT_UNVERIFIED")
            self.assertTrue(res["interaction"]["click_completed"])
            self.assertTrue(res["mouse_action_success"])
            self.assertEqual(res["interaction"]["physical_click_count"], 1)

    # -------------------------------------------------------------------------
    # CASE 7: TargetPreconditionValidator 12 Precondition Coverage
    # -------------------------------------------------------------------------
    def test_target_precondition_validator_all_12_checks(self):
        tree = UITree(screen_width=1920, screen_height=1080, stability_score=1.0)
        elem = UIElement(
            id="card_1",
            type=ElementType.VIDEO_CARD,
            bbox=BoundingBox(100, 100, 400, 300),
            visibility=VisibilityState.VISIBLE,
            interactive=True,
        )
        tree.elements[elem.id] = elem

        snapshot = UISnapshot(
            snapshot_id="SNAP-1",
            window_hwnd=1001,
            process_id=2001,
            process_name="chrome.exe",
            window_title="YouTube",
            page_type="HOME",
            timestamp=time.time(),
            viewport_size=(1920, 1080),
            detected_components=[elem],
        )

        safe_reg = build_safe_click_region({"id": "card_1", "bbox": (100, 100, 400, 300)})

        # Positive Case: All 12 pass
        val_res = TargetPreconditionValidator.validate_preconditions(
            target_element=elem,
            tree=tree,
            snapshot=snapshot,
            safe_region=safe_reg,
            local_click_point=(200, 97.5),
            screen_click_point=(300, 277),
            current_window_info={"hwnd": 1001, "pid": 2001},
            viewport_size=(1920.0, 1080.0),
        )

        self.assertTrue(val_res.valid)
        self.assertEqual(len(val_res.failed_preconditions), 0)
        self.assertEqual(val_res.status, ResolutionStatus.SUCCESS)

    # -------------------------------------------------------------------------
    # CASE 8: SafeClickRegion Bounding & Exclusion of Badges and Menus
    # -------------------------------------------------------------------------
    def test_safe_click_region_badge_and_menu_exclusion(self):
        card = {
            "id": "card_with_badges",
            "bbox": (100, 100, 442, 336),
            "children": [
                {"id": "duration_badge", "role": "badge", "bbox": (380, 180, 50, 20)},
                {"id": "menu_3dots", "role": "button", "bbox": (410, 280, 24, 24)},
            ]
        }

        safe_reg = build_safe_click_region(card)
        self.assertEqual(safe_reg.component_id, "card_with_badges")
        self.assertEqual(len(safe_reg.excluded_regions), 2)

        # Center of thumbnail (x=221, y=109) must be inside safe region
        self.assertTrue(safe_reg.contains_local_point(Point(221.0, 109.2)))

        # Point inside duration badge (x=390, y=190) must be rejected
        self.assertFalse(safe_reg.contains_local_point(Point(390.0, 190.0)))

        # Point on outer border (x=2, y=2) must be rejected (outside 5% margin)
        self.assertFalse(safe_reg.contains_local_point(Point(2.0, 2.0)))


if __name__ == "__main__":
    unittest.main()

"""
Unit & Integration Tests for:
  - Task Window Binding (Multiple Chrome Windows: YouTube vs Download History vs Settings)
  - Semantic Target & Clickable Region Resolution
  - One-Shot Physical Interaction (Zero Retry Clicks)
  - Pre-State & Post-State Verification (YouTubeState)
  - Hermes Result Propagation (CLICKED_BUT_UNVERIFIED -> success=False)
  - Video #1 to #6 Selection
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.tools.browser_context import WindowHandle, WindowSnapshot
from agent.tools.component_target import ComponentTarget, YouTubeVideoTarget, resolve_clickable_region, sort_row_major
from agent.tools.ui_interaction_service import UIInteractionService, YouTubeState
from agent.tools.window_manager import WindowIdentity, WindowInfo, WindowManager
from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.hermes_runtime import HermesRuntime


class TestTaskWindowBindingAndSemanticInteraction(unittest.TestCase):

    def setUp(self):
        self.mock_yt_window = WindowHandle(
            hwnd=2001,
            pid=1001,
            process_name="chrome.exe",
            title="Trending - YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
        )
        self.mock_downloads_window = WindowHandle(
            hwnd=2002,
            pid=1001,
            process_name="chrome.exe",
            title="Download history - Google Chrome",
            class_name="Chrome_WidgetWin_1",
        )
        self.mock_settings_window = WindowHandle(
            hwnd=2003,
            pid=1001,
            process_name="chrome.exe",
            title="Settings - Google Chrome",
            class_name="Chrome_WidgetWin_1",
        )

    def _create_mock_snapshot(self, hwnd=2001, title="YouTube - Google Chrome"):
        handle = WindowHandle(hwnd=hwnd, pid=1001, process_name="chrome.exe", title=title, class_name="Chrome_WidgetWin_1")
        return WindowSnapshot(
            handle=handle,
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

    # -------------------------------------------------------------------------
    # TEST 7: Multiple Chrome Windows (YouTube vs Download History vs Settings)
    # -------------------------------------------------------------------------
    def test_task_window_binding_prioritizes_youtube_over_downloads_and_settings(self):
        """
        When multiple Chrome windows are open (Downloads, Settings, YouTube),
        resolve_task_window MUST bind specifically to the YouTube window.
        """
        all_chrome_windows = [
            self.mock_downloads_window,
            self.mock_settings_window,
            self.mock_yt_window,
        ]

        with patch.object(WindowManager, "get_foreground_window", return_value=self.mock_downloads_window), \
             patch.object(WindowManager, "enumerate_windows", return_value=all_chrome_windows):

            resolved, reason = WindowManager.resolve_task_window(task_context="youtube", app_name="chrome")
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.hwnd, 2001)
            self.assertIn("youtube", resolved.title.lower())
            self.assertNotEqual(resolved.hwnd, self.mock_downloads_window.hwnd)
            self.assertNotEqual(resolved.hwnd, self.mock_settings_window.hwnd)

    # -------------------------------------------------------------------------
    # TESTS 1 to 6: YouTube Selection for Video #1 to Video #6
    # -------------------------------------------------------------------------
    def _test_select_video_ordinal(self, index: int):
        snap = self._create_mock_snapshot()
        mock_raw_cards = [
            {"id": f"yt_video_{i}", "bbox": (88 + (i-1)*458, 104, 442, 336), "text": f"Video #{i} Title"}
            if i <= 4 else
            {"id": f"yt_video_{i}", "bbox": (88 + (i-5)*458, 464, 442, 336), "text": f"Video #{i} Title"}
            for i in range(1, 13)
        ]

        with patch.object(WindowManager, "resolve_task_window", return_value=(self.mock_yt_window, "TASK_MATCH")), \
             patch.object(WindowManager, "validate_window", return_value=(True, "VALID")), \
             patch.object(WindowManager, "activate_window", return_value=True), \
             patch.object(WindowManager, "get_snapshot", return_value=snap), \
             patch.object(UIInteractionService, "_perceive_video_components", return_value=mock_raw_cards), \
             patch.object(MouseExecutor, "click_physical_point", return_value={
                 "success": True, "click_completed": True, "move_verified": True, "actual_position_at_click": (767, 293)
             }), \
             patch.object(UIInteractionService, "_verify_youtube_transition", return_value=(
                 True, "Title updated to 'Video Watch Page - YouTube'", YouTubeState(hwnd=2001, title="Video Watch Page - YouTube", page_type="WATCH_PAGE")
             )):

            res = UIInteractionService.select_youtube_video(index=index, wait_load=False)
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["target"]["ordinal"], index)
            self.assertEqual(res["target"]["component_id"], f"yt_video_{index}")
            self.assertEqual(res["interaction"]["physical_click_count"], 1)

    def test_select_video_1(self):
        self._test_select_video_ordinal(1)

    def test_select_video_2(self):
        self._test_select_video_ordinal(2)

    def test_select_video_3(self):
        self._test_select_video_ordinal(3)

    def test_select_video_4(self):
        self._test_select_video_ordinal(4)

    def test_select_video_5(self):
        self._test_select_video_ordinal(5)

    def test_select_video_6(self):
        self._test_select_video_ordinal(6)

    # -------------------------------------------------------------------------
    # TEST: Semantic Target & Clickable Region
    # -------------------------------------------------------------------------
    def test_resolve_clickable_region_prefers_thumbnail_over_card_center(self):
        """Clickable region should prioritize top 65% thumbnail area rather than whole card center."""
        card_dict = {
            "id": "yt_video_2",
            "bbox": (546.0, 104.0, 442.0, 336.0),
            "children": [
                {"id": "yt_video_2_thumb", "role": "thumbnail_anchor", "bbox": (0, 0, 442, 218)}
            ]
        }
        (click_x, click_y), region, child_id = resolve_clickable_region(card_dict)
        self.assertEqual(click_x, 221.0)
        self.assertEqual(click_y, 109.0)
        self.assertEqual(child_id, "yt_video_2_thumb")

    # -------------------------------------------------------------------------
    # TEST: Pre/Post State Verification Engine
    # -------------------------------------------------------------------------
    def test_youtube_state_transition_detects_watch_page(self):
        before = YouTubeState(hwnd=2001, title="YouTube - Google Chrome", page_type="HOME")
        after = YouTubeState(hwnd=2001, title="Rick Astley - Never Gonna Give You Up - YouTube", page_type="WATCH_PAGE")
        target = YouTubeVideoTarget(ordinal=2, component_id="yt_video_2", bbox=(546, 104, 442, 336), safe_click_point=(221, 109))

        with patch.object(YouTubeState, "capture", return_value=after):
            verified, reason, final_state = UIInteractionService._verify_youtube_transition(
                hwnd=2001,
                before_state=before,
                target_semantic=target,
                timeout=0.1,
            )
            self.assertTrue(verified)
            self.assertIn("Title updated", reason)

    # -------------------------------------------------------------------------
    # TEST: Hermes Result Propagation (CLICKED_BUT_UNVERIFIED -> success=False)
    # -------------------------------------------------------------------------
    def test_hermes_runtime_propagates_unverified_as_failure(self):
        runtime = HermesRuntime()

        # Mock tool execution to return CLICKED_BUT_UNVERIFIED
        unverified_tool_result = {
            "success": False,
            "status": "CLICKED_BUT_UNVERIFIED",
            "interaction": {"attempted": True, "click_completed": True},
            "target_interaction_verified": False,
            "error": "No page title transition detected",
        }

        with patch.object(runtime, "_execute_tool_sync", return_value=unverified_tool_result):
            resp = asyncio.run(runtime.run_plan(session_id="test_session", instruction="chọn video thứ 2"))
            self.assertFalse(resp.success)
            self.assertIn("playback could not be confirmed", resp.text)


if __name__ == "__main__":
    unittest.main()

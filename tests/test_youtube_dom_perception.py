"""
Unit & Integration Test Suite for YouTube DOM Perception & JavaScript Injection.

Verifies:
1. JavaScript payload structure & selector completeness (YOUTUBE_DOM_EXTRACTOR_JS).
2. Direct DOM Perception execution via ChromeDOMConnector.
3. select_youtube_video_by_dom coordinate transformation (Viewport -> Client -> Physical Screen).
4. Accurate resolution of Video 5 on responsive 3-column layouts directly from DOM.
5. Handling of out-of-range ordinals (returns TARGET_NOT_FOUND).
6. Single-click transaction dispatch (click_count = 1).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.computer_use import ComputerUseTool
from agent.tools.dom_perception import (
    DOMVideoItem,
    ChromeDOMConnector,
    YOUTUBE_DOM_EXTRACTOR_JS,
    select_youtube_video_by_dom,
)
from agent.tools.mouse_controller import MouseController
from agent.tools.window_manager import WindowHandle, WindowManager, WindowSnapshot


class TestYouTubeDOMPerception(unittest.TestCase):

    def setUp(self):
        MouseController.enable_simulation_mode(True)
        MouseController.set_simulated_position(0, 0)
        ChromeDOMConnector.set_simulated_dom_videos(None)

    def tearDown(self):
        ChromeDOMConnector.set_simulated_dom_videos(None)

    def test_javascript_payload_syntax_and_selectors(self):
        """Verify the JS payload contains all required selectors and visibility checks."""
        self.assertIn("ytd-rich-item-renderer", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("ytd-video-renderer", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("ytd-grid-video-renderer", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("ytd-compact-video-renderer", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("ytd-ad-slot-renderer", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("ytd-display-ad-renderer", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("getBoundingClientRect", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("a#thumbnail", YOUTUBE_DOM_EXTRACTOR_JS)
        self.assertIn("innerWidth", YOUTUBE_DOM_EXTRACTOR_JS)

    def test_select_youtube_video_by_dom_exact_coordinates(self):
        """
        Verify that select_youtube_video_by_dom extracts the DOM items and calculates
        exact screen coordinates for Video 5 on a 3-column layout.
        """
        mock_dom_data = [
            # Row 1 (Items 1, 2, 3)
            {"ordinal": 1, "component_id": "yt_dom_video_1", "title": "Vid 1", "href": "/watch?v=1", "center_x": 271.0, "center_y": 109.2, "bbox": [50.0, 0.0, 442.0, 218.4]},
            {"ordinal": 2, "component_id": "yt_dom_video_2", "title": "Vid 2", "href": "/watch?v=2", "center_x": 729.0, "center_y": 109.2, "bbox": [508.0, 0.0, 442.0, 218.4]},
            {"ordinal": 3, "component_id": "yt_dom_video_3", "title": "Vid 3", "href": "/watch?v=3", "center_x": 1187.0, "center_y": 109.2, "bbox": [966.0, 0.0, 442.0, 218.4]},
            # Row 2 (Items 4, 5, 6)
            {"ordinal": 4, "component_id": "yt_dom_video_4", "title": "Vid 4", "href": "/watch?v=4", "center_x": 271.0, "center_y": 469.2, "bbox": [50.0, 360.0, 442.0, 218.4]},
            {"ordinal": 5, "component_id": "yt_dom_video_5", "title": "Vid 5 - Target", "href": "/watch?v=5", "center_x": 729.0, "center_y": 469.2, "bbox": [508.0, 360.0, 442.0, 218.4]},
            {"ordinal": 6, "component_id": "yt_dom_video_6", "title": "Vid 6", "href": "/watch?v=6", "center_x": 1187.0, "center_y": 469.2, "bbox": [966.0, 360.0, 442.0, 218.4]},
        ]
        ChromeDOMConnector.set_simulated_dom_videos(mock_dom_data)

        mock_handle = WindowHandle(hwnd=99999, pid=5432, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1400, 900),
            client_rect=(0, 0, 1400, 900),
            client_screen_origin=(0, 0),
            client_size=(1400, 900),
            viewport_screen_origin=(0, 80),
            viewport_size=(1400, 820),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = select_youtube_video_by_dom(requested_ordinal=5, application="chrome")

        self.assertTrue(res["success"])
        self.assertEqual(res["ordinal"], 5)
        self.assertEqual(res["target_id"], "yt_dom_video_5")
        self.assertEqual(res["title"], "Vid 5 - Target")
        self.assertEqual(res["href"], "/watch?v=5")

        # Viewport: center_x = 729.0, center_y = 469.2
        # Screen: X = 0 + 729 = 729, Y = 0 + 80 + 469.2 = 549.2 -> 549
        expected_screen_x = 729
        expected_screen_y = int(round(80 + 469.2))  # 549
        self.assertEqual(res["click_point"], (expected_screen_x, expected_screen_y))
        self.assertTrue(res["move_verified"])
        self.assertTrue(res["click_completed"])

    def test_sponsored_card_counted_as_ordinal_one(self):
        """Verify that sponsored card in first slot is retained and selected as Ordinal #1."""
        mock_dom_data = [
            {"ordinal": 1, "component_id": "yt_dom_video_1", "title": "Sponsored Ad Product", "href": "/ad_click", "center_x": 271.0, "center_y": 109.2, "bbox": [50.0, 0.0, 442.0, 218.4]},
            {"ordinal": 2, "component_id": "yt_dom_video_2", "title": "Regular Video 1", "href": "/watch?v=2", "center_x": 729.0, "center_y": 109.2, "bbox": [508.0, 0.0, 442.0, 218.4]},
        ]
        ChromeDOMConnector.set_simulated_dom_videos(mock_dom_data)

        mock_handle = WindowHandle(hwnd=99999, pid=5432, process_name="chrome.exe", title="YouTube", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1400, 900),
            client_rect=(0, 0, 1400, 900),
            client_screen_origin=(0, 0),
            client_size=(1400, 900),
            viewport_screen_origin=(0, 80),
            viewport_size=(1400, 820),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = select_youtube_video_by_dom(requested_ordinal=1, application="chrome")

        self.assertTrue(res["success"])
        self.assertEqual(res["ordinal"], 1)
        self.assertEqual(res["title"], "Sponsored Ad Product")
        self.assertEqual(res["click_point"], (271, int(round(80 + 109.2))))

    def test_out_of_range_ordinal_returns_target_not_found(self):
        """Verify requesting index 10 when DOM has 6 items cleanly returns TARGET_NOT_FOUND."""
        mock_dom_data = [
            {"ordinal": 1, "component_id": "yt_dom_video_1", "center_x": 200.0, "center_y": 150.0, "bbox": [50.0, 50.0, 300.0, 200.0]},
            {"ordinal": 2, "component_id": "yt_dom_video_2", "center_x": 550.0, "center_y": 150.0, "bbox": [400.0, 50.0, 300.0, 200.0]},
        ]
        ChromeDOMConnector.set_simulated_dom_videos(mock_dom_data)

        mock_handle = WindowHandle(hwnd=99999, pid=5432, process_name="chrome.exe", title="YouTube", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1400, 900),
            client_rect=(0, 0, 1400, 900),
            client_screen_origin=(0, 0),
            client_size=(1400, 900),
            viewport_screen_origin=(0, 80),
            viewport_size=(1400, 820),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = select_youtube_video_by_dom(requested_ordinal=10, application="chrome")

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "TARGET_NOT_FOUND")

    def test_computer_use_tool_integration(self):
        """Verify ComputerUseTool.select_youtube_video_by_dom delegates correctly."""
        mock_dom_data = [
            {"ordinal": 1, "component_id": "yt_dom_video_1", "title": "First Video", "href": "/watch?v=first", "center_x": 300.0, "center_y": 200.0, "bbox": [100.0, 50.0, 400.0, 300.0]},
        ]
        ChromeDOMConnector.set_simulated_dom_videos(mock_dom_data)

        mock_handle = WindowHandle(hwnd=88888, pid=1111, process_name="chrome.exe", title="YouTube - Google Chrome", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1920, 1080),
            client_rect=(0, 0, 1920, 1080),
            client_screen_origin=(0, 0),
            client_size=(1920, 1080),
            viewport_screen_origin=(0, 85),
            viewport_size=(1920, 995),
            browser_chrome_height=85,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = ComputerUseTool.select_youtube_video_by_dom(requested_ordinal=1)

        self.assertTrue(res["success"])
        self.assertEqual(res["click_point"], (300, 285))

    def test_dom_extraction_empty_fails_fast_with_no_fallback(self):
        """
        Verify that when DOM extraction returns 0 items, select_youtube_video_by_dom
        fails fast immediately with status DOM_EXTRACTION_FAILED and clear error message (NO fallback).
        """
        ChromeDOMConnector.set_simulated_dom_videos([])

        mock_handle = WindowHandle(hwnd=99999, pid=5432, process_name="chrome.exe", title="YouTube", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1400, 900),
            client_rect=(0, 0, 1400, 900),
            client_screen_origin=(0, 0),
            client_size=(1400, 900),
            viewport_screen_origin=(0, 80),
            viewport_size=(1400, 820),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = select_youtube_video_by_dom(requested_ordinal=1, application="chrome")

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "DOM_EXTRACTION_FAILED")
        self.assertEqual(res["total_dom_items"], 0)
        self.assertEqual(res["message"], "DOM Extraction failed: 0 items returned")

    def test_debug_logging_and_coord_math_printed(self):
        """
        Verify that debug_log is populated and the exact coordinate transformation math
        string is generated and printed.
        """
        mock_payload = {
            "videos": [
                {
                    "ordinal": 1,
                    "component_id": "yt_video_1",
                    "title": "First Video",
                    "href": "/watch?v=first",
                    "center_x": 300.0,
                    "center_y": 150.0,
                    "bbox": [50.0, 50.0, 500.0, 200.0],
                }
            ],
            "debug_log": [
                "Viewport dimensions: innerWidth=1400, innerHeight=900",
                "Total nodes queried: 5",
                "Skipped index 1 (ytd-rich-item-renderer): rect.right (1600.0) > innerWidth (1400)",
                "Accepted index 0 (ytd-rich-item-renderer) as ordinal #1: center=(300.0, 150.0), title=\"First Video\"",
                "DOM Extraction finished: 1 visible videos identified.",
            ]
        }
        ChromeDOMConnector.set_simulated_dom_videos(mock_payload)

        mock_handle = WindowHandle(hwnd=99999, pid=5432, process_name="chrome.exe", title="YouTube", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(100, 50, 1500, 950),
            client_rect=(0, 0, 1400, 900),
            client_screen_origin=(100, 50),
            client_size=(1400, 900),
            viewport_screen_origin=(100, 130),
            viewport_size=(1400, 820),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = select_youtube_video_by_dom(requested_ordinal=1, application="chrome", dry_run=True)

        self.assertTrue(res["success"])
        self.assertEqual(res["click_point"], (400, 280))  # 100 + 300 = 400, 50 + 150 + 80 = 280
        self.assertIn("debug_log", res)
        self.assertEqual(len(res["debug_log"]), 5)
        self.assertIn("[COORD MATH] Viewport (cx: 300.0, cy: 150.0) -> Screen (X: 100 + 300.0 = 400, Y: 50 + 150.0 + 80 = 280)", res["coord_math"])

    def test_tier_2_uia_fallback_when_cdp_fails(self):
        """
        Verify that when Tier 1 (CDP) fails/times out, system automatically activates Tier 2 (UIA)
        and extracts video cards from Chromium Accessibility Tree.
        """
        from agent.tools.uia_dom_extractor import UIADOMExtractor

        ChromeDOMConnector.set_simulated_dom_videos(None)
        UIADOMExtractor.set_simulated_cards([
            {"ordinal": 1, "title": "UIA Video 1", "screen_x": 300, "screen_y": 250, "bbox": (100, 150, 500, 350)},
            {"ordinal": 2, "title": "UIA Video 2 - Target", "screen_x": 750, "screen_y": 250, "bbox": (550, 150, 950, 350)},
        ])

        mock_handle = WindowHandle(hwnd=99999, pid=5432, process_name="chrome.exe", title="YouTube", class_name="Chrome_WidgetWin_1")
        mock_snap = WindowSnapshot(
            handle=mock_handle,
            window_rect=(0, 0, 1400, 900),
            client_rect=(0, 0, 1400, 900),
            client_screen_origin=(0, 0),
            client_size=(1400, 900),
            viewport_screen_origin=(0, 80),
            viewport_size=(1400, 820),
            browser_chrome_height=80,
            dpi=96,
            dpi_scale=1.0,
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
        )

        with patch("urllib.request.urlopen", side_effect=Exception("CDP Port Unavailable")), \
             patch.object(WindowManager, "resolve_target", return_value=(mock_handle, "TARGET_LOCKED")), \
             patch.object(WindowManager, "get_snapshot", return_value=mock_snap):

            res = select_youtube_video_by_dom(requested_ordinal=2, application="chrome")

        self.assertTrue(res["success"])
        self.assertEqual(res["ordinal"], 2)
        self.assertEqual(res["title"], "UIA Video 2 - Target")
        self.assertEqual(res["click_point"], (750, 250))
        self.assertTrue(res["click_completed"])
        UIADOMExtractor.set_simulated_cards(None)


if __name__ == "__main__":
    unittest.main()

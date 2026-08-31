"""
Unit & Integration Tests for Browser Process / Window Lifecycle / HWND Stability.
Verifies compliance with the FIX SPECIFICATION:
- Test A: Existing valid Chrome window (same session, valid HWND, correct target recalculation).
- Test B: Chrome window changes (stale HWND detected, recovery resolves new HWND, geometry recalculated, UI re-perceived, new coordinates clicked).
- Test C: Browser window disappears/minimized (stale detected, recovery attempted, no click on stale coordinates, clean failure).
- Test D: Mouse click succeeds physically but YouTube interaction does not react (Level 1 True, Level 2 False, Level 3 False, overall success False).
- Multi-Attribute Validation: PID mismatch, process name mismatch, minimized state, handle destruction.
"""

from __future__ import annotations

import logging
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.browser_tool import BrowserTool
from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.tools.mouse_controller import MouseController
from agent.tools.window_target_resolver import (
    BrowserSession,
    BrowserSessionState,
    TargetResolutionSource,
    WindowTargetResolver,
)
from agent.ui_perception.coordinates import (
    Coordinate,
    CoordinateResolver,
    CoordinateSpace,
    PhysicalScreenPoint,
    WindowGeometry,
    WindowGeometryProvider,
)
from agent.tools.dom_perception import ChromeDOMConnector
from agent.ui_perception.models import BoundingBox, ElementType, UIElement, UITree
from agent.ui_perception.service import HermesUIService


class TestBrowserLifecycleHWNDStability(unittest.TestCase):

    def setUp(self):
        WindowTargetResolver.release_target()
        WindowTargetResolver._browser_session = None
        WindowTargetResolver._last_snapshot = None
        WindowTargetResolver._last_user_active_window = None
        WindowTargetResolver._window_history.clear()
        MouseController.set_simulated_position(100, 100)
        ChromeDOMConnector.set_simulated_dom_videos([
            {"ordinal": 1, "component_id": "yt_video_card_1", "title": "Video 1", "href": "/watch?v=1", "center_x": 300.0, "center_y": 200.0, "bbox": [50, 50, 442, 336]},
            {"ordinal": 2, "component_id": "yt_video_card_2", "title": "Video 2", "href": "/watch?v=2", "center_x": 750.0, "center_y": 200.0, "bbox": [500, 50, 442, 336]},
            {"ordinal": 3, "component_id": "yt_video_card_3", "title": "Video 3", "href": "/watch?v=3", "center_x": 1200.0, "center_y": 200.0, "bbox": [950, 50, 442, 336]},
            {"ordinal": 4, "component_id": "yt_video_card_4", "title": "Video 4", "href": "/watch?v=4", "center_x": 1650.0, "center_y": 200.0, "bbox": [1400, 50, 442, 336]},
        ])

    def tearDown(self):
        ChromeDOMConnector.set_simulated_dom_videos(None)

    def _create_mock_tree(self, video_count: int = 4) -> UITree:
        tree = UITree(
            screen_width=1920,
            screen_height=1080,
            window_title="YouTube - Google Chrome",
            app_name="chrome",
            is_browser=True,
            stability_score=1.0,
        )
        for i in range(1, video_count + 1):
            col = (i - 1) % 4
            row = (i - 1) // 4
            x = 50.0 + col * 450.0
            y = 104.0 + row * 320.0
            elem = UIElement(
                id=f"yt_video_card_{i}",
                text=f"Video {i}",
                type=ElementType.VIDEO_CARD,
                bbox=BoundingBox(x=x, y=y, width=420.0, height=280.0, space=CoordinateSpace.VIEWPORT_SPACE),
                interactive=True,
            )
            tree.elements[elem.id] = elem
        return tree

    def test_case_a_existing_chrome_window(self):
        """
        Test A — Existing Chrome window:
        Select video 1, then video 2, then video 3 in the same valid browser session.
        Verifies:
        - Same valid browser session is preserved.
        - HWND is validated and remains valid.
        - Target coordinates are recalculated correctly for each ordinal.
        """
        session_hwnd = 85330818
        session_pid = 12345
        session_title = "YouTube - Google Chrome"

        session = BrowserSession(
            process_name="chrome.exe",
            pid=session_pid,
            hwnd=session_hwnd,
            title=session_title,
            created_at=time.time(),
            last_validated_at=time.time(),
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)

        geom = WindowGeometry(
            hwnd=session_hwnd,
            title=session_title,
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

        mock_tree = self._create_mock_tree(video_count=4)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(True, "VALID")), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(session_title, session_pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=mock_tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            # Click Video 1
            res1 = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
            self.assertTrue(res1["mouse_action_success"])
            self.assertEqual(res1["target_id"], "yt_video_card_1")
            pt1 = res1["click_point"]

            # Click Video 2
            res2 = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
            self.assertTrue(res2["mouse_action_success"])
            self.assertEqual(res2["target_id"], "yt_video_card_2")
            pt2 = res2["click_point"]

            # Click Video 3
            res3 = ComputerUseTool.select_youtube_video(index=3, wait_load=False)
            self.assertTrue(res3["mouse_action_success"])
            self.assertEqual(res3["target_id"], "yt_video_card_3")
            pt3 = res3["click_point"]

            # Coordinates must be distinct and increasing from left to right
            self.assertLess(pt1[0], pt2[0])
            self.assertLess(pt2[0], pt3[0])
            # Session HWND remained stable
            active_session = WindowTargetResolver.get_browser_session()
            self.assertIsNotNone(active_session)
            self.assertEqual(active_session.hwnd, session_hwnd)

    def test_case_b_chrome_window_changes_recovery(self):
        """
        Test B — Chrome window changes:
        1. Stored HWND is stale (closed or PID mismatch).
        2. WindowTargetResolver detects stale HWND and recovers new Chrome window.
        3. Window geometry is recalculated for new HWND.
        4. UI is re-perceived on the new window.
        5. Coordinates are computed from the new window and clicked.
        """
        old_hwnd = 11111111
        old_pid = 5000
        new_hwnd = 22222222
        new_pid = 6000
        new_title = "YouTube - Google Chrome"

        # Initialize with stale session
        stale_session = BrowserSession(
            process_name="chrome.exe",
            pid=old_pid,
            hwnd=old_hwnd,
            title="Old YouTube",
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(stale_session)

        # Candidate Chrome windows for recovery
        valid_windows = [
            (new_hwnd, new_title, new_pid, "chrome.exe", 1920, 1080),
        ]

        new_geom = WindowGeometry(
            hwnd=new_hwnd,
            title=new_title,
            is_valid=True,
            window_rect=(100, 100, 2020, 1180),
            window_x=100,
            window_y=100,
            window_width=1920,
            window_height=1080,
            client_rect=(0, 0, 1920, 1080),
            client_width=1920,
            client_height=1080,
            client_screen_x=100,
            client_screen_y=100,
            browser_chrome_height=80,
            viewport_screen_x=100,
            viewport_screen_y=180,
            viewport_width=1920,
            viewport_height=1000,
            dpi=96,
            dpi_scale=1.0,
        )

        mock_tree = self._create_mock_tree(video_count=4)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "find_valid_user_windows", return_value=valid_windows), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(new_title, new_pid, "chrome.exe", (100, 100, 2020, 1180), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=new_geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=mock_tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}) as mock_click:

            # Make validation fail on old_hwnd, but succeed on new_hwnd
            def mock_validate(session=None, check_minimized=True):
                sess = session or WindowTargetResolver._browser_session
                if sess and sess.hwnd == old_hwnd:
                    return False, "PID_MISMATCH"
                return True, "VALID"

            with patch.object(WindowTargetResolver, "validate_browser_session", side_effect=mock_validate):
                res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)

                self.assertTrue(res["mouse_action_success"])
                self.assertTrue(res["window_recovered"])
                self.assertEqual(res["target_id"], "yt_video_card_2")

                # Verify new session is locked
                current_session = WindowTargetResolver.get_browser_session()
                self.assertIsNotNone(current_session)
                self.assertEqual(current_session.hwnd, new_hwnd)
                self.assertEqual(current_session.pid, new_pid)

                # Verify click was made using coordinates shifted by the new window origin (+100)
                click_x, click_y = res["click_point"]
                self.assertGreaterEqual(click_x, 100)
                self.assertGreaterEqual(click_y, 100)

    def test_case_c_browser_window_disappears(self):
        """
        Test C — Browser window disappears/minimized:
        Target Chrome window is closed/minimized and no other Chrome window exists.
        Expected:
        - Stale window detected.
        - Recovery attempted.
        - Clean failure without clicking stale coordinates.
        """
        stale_session = BrowserSession(
            process_name="chrome.exe",
            pid=9999,
            hwnd=12345678,
            title="YouTube",
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(stale_session)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(False, "WINDOW_NOT_VISIBLE")), \
             patch.object(WindowTargetResolver, "find_valid_user_windows", return_value=[]), \
             patch.object(MouseExecutor, "click_physical_point") as mock_click:

            res = ComputerUseTool.select_youtube_video(index=1, wait_load=False)

            self.assertFalse(res["success"])
            self.assertFalse(res["mouse_action_success"])
            self.assertEqual(res["status"], "WINDOW_NOT_FOUND")
            # Mouse click must NEVER be executed against stale/non-existent window
            self.assertFalse(mock_click.called)

    def test_case_d_mouse_click_succeeds_but_interaction_unverified(self):
        """
        Test D — Click succeeds physically, but YouTube does not react:
        Expected:
        - mouse_action_success = True
        - target_interaction_verified = False
        - task_verified = False
        - success = False
        - Must NOT report overall success = True!
        """
        session_hwnd = 77777777
        session_pid = 8888
        session_title = "YouTube - Google Chrome"

        session = BrowserSession(
            process_name="chrome.exe",
            pid=session_pid,
            hwnd=session_hwnd,
            title=session_title,
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)

        geom = WindowGeometry(
            hwnd=session_hwnd,
            title=session_title,
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

        mock_tree = self._create_mock_tree(video_count=4)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(True, "VALID")), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(session_title, session_pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=mock_tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)

            # Level 1 succeeded (physical mouse click)
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["click_completed"])

            # Level 2 & 3 failed (no page transition / title unchanged)
            self.assertFalse(res["target_interaction_verified"])
            self.assertFalse(res["task_verified"])

            # Overall must be False (NOT converted to True!)
            self.assertFalse(res["success"])
            self.assertEqual(res["failure_reason"], "post_click_verification_failed")
            self.assertIn("playback could not be confirmed", res["message"])

    def test_case_d2_click_succeeds_and_interaction_verified(self):
        """
        Test D2 — Click succeeds and YouTube interaction is verified:
        Expected:
        - mouse_action_success = True
        - target_interaction_verified = True
        - task_verified = True
        - success = True
        """
        session_hwnd = 77777777
        session_pid = 8888
        session_title = "YouTube - Google Chrome"
        post_title = "Rick Astley - Never Gonna Give You Up - YouTube"

        session = BrowserSession(
            process_name="chrome.exe",
            pid=session_pid,
            hwnd=session_hwnd,
            title=session_title,
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)

        geom = WindowGeometry(
            hwnd=session_hwnd,
            title=session_title,
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

        mock_tree = self._create_mock_tree(video_count=4)

        # Meta mock returns initial title first, then updated watch title post-click
        def mock_get_meta(hwnd):
            if hasattr(mock_get_meta, "called"):
                return (post_title, session_pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)
            mock_get_meta.called = True
            return (session_title, session_pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(True, "VALID")), \
             patch.object(WindowTargetResolver, "get_window_meta", side_effect=mock_get_meta), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=mock_tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)

            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["target_interaction_verified"])
            self.assertTrue(res["task_verified"])
            self.assertTrue(res["success"])
            self.assertIn("Clicked and played YouTube video 2", res["message"])

    def test_multi_attribute_pid_mismatch_detection(self):
        """Test multi-attribute validation detects PID mismatch as stale."""
        session = BrowserSession(
            process_name="chrome.exe",
            pid=1234,
            hwnd=99999,
            title="Chrome",
        )

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.IsWindow", return_value=True), \
                 patch.object(WindowTargetResolver, "is_valid_interactive_target", return_value=True), \
                 patch("ctypes.windll.user32.IsWindowVisible", return_value=True), \
                 patch("ctypes.windll.user32.IsIconic", return_value=False), \
                 patch.object(WindowTargetResolver, "is_cloaked", return_value=False), \
                 patch("ctypes.windll.user32.GetWindowThreadProcessId") as mock_pid:

                def set_pid(hwnd, byref_pid):
                    import ctypes
                    ctypes.cast(byref_pid, ctypes.POINTER(ctypes.c_ulong)).contents.value = 5678  # Different PID!
                    return 1

                mock_pid.side_effect = set_pid

                is_valid, reason = WindowTargetResolver.validate_browser_session(session)
                self.assertFalse(is_valid)
                self.assertEqual(reason, "PID_MISMATCH")
                self.assertEqual(session.state, BrowserSessionState.STALE.value)

    def test_multi_attribute_minimized_window_detection(self):
        """Test multi-attribute validation detects minimized window as stale."""
        session = BrowserSession(
            process_name="chrome.exe",
            pid=1234,
            hwnd=99999,
            title="Chrome",
        )

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.IsWindow", return_value=True), \
                 patch("ctypes.windll.user32.IsWindowVisible", return_value=True), \
                 patch("ctypes.windll.user32.IsIconic", return_value=True):  # Minimized!

                is_valid, reason = WindowTargetResolver.validate_browser_session(session, check_minimized=True)
                self.assertFalse(is_valid)
                self.assertEqual(reason, "WINDOW_MINIMIZED")
                self.assertEqual(session.state, BrowserSessionState.STALE.value)


if __name__ == "__main__":
    unittest.main()

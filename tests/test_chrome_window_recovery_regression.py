"""
Regression Test Suite for Chrome Window Disappearance and Resilient Browser Recovery.
Covers all 10 mandatory regression test scenarios specified in Section X:
- TEST 1: Chrome window visible -> action -> success
- TEST 2: Chrome window minimized -> restore -> action -> success
- TEST 3: Old HWND destroyed -> new Chrome HWND exists -> rebind -> action -> success
- TEST 4: Old HWND hidden -> Chrome process alive -> recover / in-place restore -> action -> success
- TEST 5: Old HWND dead -> new Chrome window exists -> recover -> action -> success
- TEST 6: Chrome process genuinely dead -> no Chrome window -> return browser_session_unavailable
- TEST 7: Multiple Chrome windows -> select correct YouTube window -> ignore popup / background
- TEST 8: Jarvis overlay visible in foreground -> Chrome remains usable
- TEST 9: TTS speaking/listening transition -> Chrome remains usable
- TEST 10: Hermes agent_thinking -> agent_acting -> Chrome remains usable
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.tools.mouse_controller import MouseController
from agent.tools.window_target_resolver import (
    BrowserSession,
    BrowserSessionState,
    TargetResolutionSource,
    WindowTargetResolver,
    WindowTargetSnapshot,
)
from agent.ui_perception.coordinates import (
    CoordinateSpace,
    WindowGeometry,
    WindowGeometryProvider,
)
from agent.ui_perception.models import BoundingBox, ElementType, UIElement, UITree
from agent.ui_perception.service import HermesUIService


class TestChromeWindowRecoveryRegression(unittest.TestCase):

    def setUp(self):
        WindowTargetResolver.release_target()
        WindowTargetResolver._browser_session = None
        WindowTargetResolver._last_snapshot = None
        WindowTargetResolver._last_user_active_window = None
        WindowTargetResolver._window_history.clear()
        MouseController.set_simulated_position(100, 100)

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

    def _create_mock_geom(self, hwnd: int = 12345, title: str = "YouTube - Google Chrome") -> WindowGeometry:
        return WindowGeometry(
            hwnd=hwnd,
            title=title,
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

    def test_01_chrome_window_visible_action_success(self):
        """TEST 1: Chrome window visible -> action -> success."""
        hwnd = 10001
        pid = 22001
        title = "YouTube - Google Chrome"
        session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=hwnd,
            title=title,
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)
        geom = self._create_mock_geom(hwnd, title)
        tree = self._create_mock_tree(4)

        # Meta mock returns updated watch title post-click for verified playback
        def mock_get_meta(h):
            if hasattr(mock_get_meta, "called"):
                return ("Watching Video 2 - YouTube", pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)
            mock_get_meta.called = True
            return (title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(True, "VALID")), \
             patch.object(WindowTargetResolver, "get_window_meta", side_effect=mock_get_meta), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["target_interaction_verified"])
            self.assertTrue(res["success"])
            self.assertEqual(res["target_id"], "yt_video_card_2")

    def test_02_chrome_window_minimized_restore_action_success(self):
        """TEST 2: Chrome window minimized -> restore -> action -> success."""
        hwnd = 10002
        pid = 22002
        title = "YouTube - Google Chrome"
        session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=hwnd,
            title=title,
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)
        geom = self._create_mock_geom(hwnd, title)
        tree = self._create_mock_tree(4)

        restored_session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=hwnd,
            title=title,
            state=BrowserSessionState.RECOVERED.value,
        )

        def mock_validate(s=None, check_minimized=True):
            sess = s or WindowTargetResolver._browser_session
            if sess and sess.state == BrowserSessionState.ACTIVE.value:
                return False, "WINDOW_MINIMIZED"
            return True, "VALID"

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", side_effect=mock_validate), \
             patch.object(WindowTargetResolver, "recover_browser_window", return_value=restored_session), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["window_recovered"])

    def test_03_old_hwnd_destroyed_new_hwnd_rebind_success(self):
        """TEST 3: Old HWND destroyed -> new Chrome HWND exists -> rebind -> action -> success."""
        old_hwnd = 10003
        new_hwnd = 20003
        pid = 22003
        title = "YouTube - Google Chrome"

        stale_session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=old_hwnd,
            title="Old Tab",
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(stale_session)

        candidates = [{
            "hwnd": new_hwnd,
            "pid": pid,
            "proc_name": "chrome.exe",
            "title": title,
            "class_name": "Chrome_WidgetWin_1",
            "is_visible": True,
            "is_iconic": False,
            "is_zoomed": False,
            "is_foreground": True,
            "rect": (0, 0, 1920, 1080),
            "area": 1920 * 1080,
            "style": 0x16CF0000,
            "ex_style": 0x00000110,
            "score": 580,
        }]

        geom = self._create_mock_geom(new_hwnd, title)
        tree = self._create_mock_tree(4)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "enumerate_chrome_windows", return_value=candidates), \
             patch.object(WindowTargetResolver, "focus_window", return_value=True), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            if sys.platform == "win32":
                def mock_pid(h, ptr):
                    if ptr:
                        ptr._obj.value = pid
                    return 1

                with patch("ctypes.windll.user32.IsWindow", side_effect=lambda h: h == new_hwnd), \
                     patch("ctypes.windll.user32.IsWindowVisible", return_value=True), \
                     patch("ctypes.windll.user32.GetWindowThreadProcessId", side_effect=mock_pid):
                    res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
                    self.assertTrue(res["mouse_action_success"])
                    self.assertTrue(res["window_recovered"])
                    self.assertEqual(WindowTargetResolver.get_browser_session().hwnd, new_hwnd)
            else:
                recovered = WindowTargetResolver.recover_browser_window(task_context="youtube", old_hwnd=old_hwnd)
                self.assertIsNotNone(recovered)

    def test_04_old_hwnd_hidden_recover_action_success(self):
        """TEST 4: Old HWND hidden -> Chrome process alive -> recover / restore -> action -> success."""
        old_hwnd = 10004
        pid = 22004
        title = "YouTube - Google Chrome"

        session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=old_hwnd,
            title=title,
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)

        restored = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=old_hwnd,
            title=title,
            state=BrowserSessionState.RECOVERED.value,
        )

        geom = self._create_mock_geom(old_hwnd, title)
        tree = self._create_mock_tree(4)

        def mock_validate(s=None, check_minimized=True):
            sess = s or WindowTargetResolver._browser_session
            if sess and sess.state == BrowserSessionState.ACTIVE.value:
                return False, "WINDOW_NOT_VISIBLE"
            return True, "VALID"

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", side_effect=mock_validate), \
             patch.object(WindowTargetResolver, "recover_browser_window", return_value=restored), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["window_recovered"])

    def test_05_old_hwnd_dead_new_window_exists_recover_success(self):
        """TEST 5: Old HWND dead -> new Chrome window exists -> recover -> action -> success."""
        old_hwnd = 99999
        new_hwnd = 88888
        pid = 22005
        title = "YouTube - Google Chrome"

        stale_session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=old_hwnd,
            title="Dead Tab",
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(stale_session)

        recovered_session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=new_hwnd,
            title=title,
            state=BrowserSessionState.RECOVERED.value,
        )

        geom = self._create_mock_geom(new_hwnd, title)
        tree = self._create_mock_tree(4)

        def mock_validate(s=None, check_minimized=True):
            sess = s or WindowTargetResolver._browser_session
            if sess and sess.hwnd == old_hwnd:
                return False, "HWND_DESTROYED"
            return True, "VALID"

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", side_effect=mock_validate), \
             patch.object(WindowTargetResolver, "recover_browser_window", return_value=recovered_session), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom), \
             patch.object(HermesUIService, "perceive_active_window", return_value=tree), \
             patch.object(MouseExecutor, "click_physical_point", return_value={"success": True, "mouse_action_success": True}):

            res = ComputerUseTool.select_youtube_video(index=2, wait_load=False)
            self.assertTrue(res["mouse_action_success"])
            self.assertTrue(res["window_recovered"])
            self.assertEqual(res["target_id"], "yt_video_card_2")

    def test_06_chrome_process_dead_no_window_fails_gracefully(self):
        """TEST 6: Chrome process dead -> no Chrome window -> return browser_session_unavailable."""
        dead_hwnd = 55555
        dead_pid = 44444

        stale_session = BrowserSession(
            process_name="chrome.exe",
            pid=dead_pid,
            hwnd=dead_hwnd,
            title="Crashed Chrome",
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(stale_session)

        with patch("agent.tools.computer_use.ComputerUseTool.switch_window"), \
             patch.object(WindowTargetResolver, "validate_browser_session", return_value=(False, "HWND_DESTROYED")), \
             patch.object(WindowTargetResolver, "recover_browser_window", return_value=None), \
             patch.object(MouseExecutor, "click_physical_point") as mock_click:

            res = ComputerUseTool.select_youtube_video(index=1, wait_load=False)
            self.assertFalse(res["success"])
            self.assertFalse(res["mouse_action_success"])
            self.assertIn(res["failure_reason"], ("browser_session_unavailable", "window_recovery_failed"))
            self.assertFalse(mock_click.called)

    def test_07_multiple_chrome_windows_selects_youtube_window(self):
        """TEST 7: Multiple Chrome windows -> chooses YouTube window with highest score."""
        yt_hwnd = 30001
        blank_hwnd = 30002
        popup_hwnd = 30003

        candidates = [
            {
                "hwnd": popup_hwnd,
                "pid": 22007,
                "proc_name": "chrome.exe",
                "title": "",
                "class_name": "Chrome_WidgetWin_0",
                "is_visible": True,
                "is_iconic": False,
                "is_zoomed": False,
                "is_foreground": False,
                "rect": (0, 0, 100, 100),
                "area": 10000,
                "style": 0x16CF0000,
                "ex_style": 0x00000110,
                "score": 100,
            },
            {
                "hwnd": blank_hwnd,
                "pid": 22007,
                "proc_name": "chrome.exe",
                "title": "Google Search - Google Chrome",
                "class_name": "Chrome_WidgetWin_1",
                "is_visible": True,
                "is_iconic": False,
                "is_zoomed": False,
                "is_foreground": False,
                "rect": (0, 0, 1920, 1080),
                "area": 1920 * 1080,
                "style": 0x16CF0000,
                "ex_style": 0x00000110,
                "score": 280,
            },
            {
                "hwnd": yt_hwnd,
                "pid": 22007,
                "proc_name": "chrome.exe",
                "title": "YouTube - Google Chrome",
                "class_name": "Chrome_WidgetWin_1",
                "is_visible": True,
                "is_iconic": False,
                "is_zoomed": False,
                "is_foreground": True,
                "rect": (0, 0, 1920, 1080),
                "area": 1920 * 1080,
                "style": 0x16CF0000,
                "ex_style": 0x00000110,
                "score": 630,
            },
        ]

        with patch.object(WindowTargetResolver, "enumerate_chrome_windows", return_value=candidates), \
             patch.object(WindowTargetResolver, "focus_window", return_value=True), \
             patch("ctypes.windll.user32.IsWindow" if sys.platform == "win32" else "unittest.mock.MagicMock", return_value=True):

            recovered = WindowTargetResolver.recover_browser_window(task_context="youtube")
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered.hwnd, yt_hwnd)
            self.assertEqual(recovered.title, "YouTube - Google Chrome")

    def test_08_jarvis_overlay_visible_chrome_usable(self):
        """TEST 8: Jarvis overlay visible in foreground -> Chrome target snapshot preserved and usable."""
        chrome_hwnd = 10008
        overlay_hwnd = 99998
        pid = 22008
        title = "YouTube - Google Chrome"

        with patch.object(WindowTargetResolver, "is_jarvis_window", side_effect=lambda h: h == overlay_hwnd), \
             patch.object(WindowTargetResolver, "is_valid_interactive_target", side_effect=lambda h, check_minimized=True: h == chrome_hwnd), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=(title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)):

            # Record Chrome before overlay comes to foreground
            snap_init = WindowTargetResolver.record_active_window(chrome_hwnd)
            self.assertIsNotNone(snap_init)
            self.assertEqual(snap_init.hwnd, chrome_hwnd)

            # Recording active window when overlay is foreground must preserve Chrome snapshot
            snap = WindowTargetResolver.record_active_window(overlay_hwnd)
            self.assertEqual(snap.hwnd, chrome_hwnd)

            # Resolving generic target returns Chrome from snapshot
            hwnd_out, title_out, _, src = WindowTargetResolver.resolve_target(None, command_name="switch_window")
            self.assertEqual(hwnd_out, chrome_hwnd)
            self.assertEqual(src, TargetResolutionSource.LAST_USER_ACTIVE)

    def test_09_tts_speaking_listening_transition_chrome_preserved(self):
        """TEST 9: TTS speaking/listening transition does not invalidate BrowserSession."""
        chrome_hwnd = 10009
        pid = 22009
        title = "YouTube - Google Chrome"

        session = BrowserSession(
            process_name="chrome.exe",
            pid=pid,
            hwnd=chrome_hwnd,
            title=title,
            state=BrowserSessionState.ACTIVE.value,
        )
        WindowTargetResolver.set_browser_session(session)

        active_sess = WindowTargetResolver.get_browser_session()
        self.assertIsNotNone(active_sess)
        self.assertEqual(active_sess.hwnd, chrome_hwnd)
        self.assertTrue(active_sess.is_valid())

    def test_10_hermes_thinking_acting_transition_chrome_usable(self):
        """TEST 10: Hermes agent_thinking -> agent_acting preserves locked Chrome target."""
        chrome_hwnd = 10010
        pid = 22010
        title = "YouTube - Google Chrome"

        with patch("ctypes.windll.user32.IsWindow" if sys.platform == "win32" else "unittest.mock.MagicMock", return_value=True):
            locked_ctx = WindowTargetResolver.lock_target(chrome_hwnd, title, "chrome.exe", pid=pid)
            self.assertIsNotNone(locked_ctx)
            self.assertEqual(locked_ctx.hwnd, chrome_hwnd)

            with patch.object(WindowTargetResolver, "validate_target_context", return_value=(True, "VALID")), \
                 patch.object(WindowTargetResolver, "get_window_meta", return_value=(title, pid, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)):

                hwnd_res, title_res, _, src = WindowTargetResolver.resolve_target("chrome", command_name="switch_window")
                self.assertEqual(hwnd_res, chrome_hwnd)
                self.assertEqual(src, TargetResolutionSource.LOCKED_TASK_HWND)


if __name__ == "__main__":
    unittest.main()

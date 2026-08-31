"""
Comprehensive Test Suite for Jarvis Window & Tab Management.

Covers all 9 mandatory specification test scenarios:
- Test 1: User in Chrome -> Jarvis overlay foreground -> "đóng cửa sổ này" -> Chrome closed (Jarvis preserved)
- Test 2: User in VS Code -> Jarvis overlay foreground -> "close window" -> VS Code closed
- Test 3: Foreground = Jarvis, Last user window = Chrome, Task Manager open -> "đóng cửa sổ" -> Chrome closed (Task Manager untouched)
- Test 4: Last snapshot HWND was closed -> fallback to next valid user window without crashing
- Test 5: No valid target available -> success=False, speech response reports failure without saying "Closing window."
- Test 6: Chrome with 3 tabs -> "chuyển sang tab thứ 2" -> TAB_MANAGEMENT called with index 2, close_window NOT called
- Test 7: 3 application windows -> "chuyển sang cửa sổ thứ 2" -> deterministic spatial ordering picks exact 2nd window
- Test 8: "đóng tab này" -> CLOSE_TAB (Ctrl+W) executed, close_window NOT called
- Test 9: Tool returns success=False -> Hermes runtime returns AgentResponse(success=False) and truth-preserving speech
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.hermes_runtime import HermesRuntime
from agent.tools.computer_use import ComputerUseTool
from agent.tools.window_target_resolver import (
    TargetResolutionSource,
    WindowTargetResolver,
    WindowTargetSnapshot,
)


class TestWindowTabManagement(unittest.TestCase):

    def setUp(self):
        WindowTargetResolver._last_user_active_window = None
        WindowTargetResolver._window_history.clear()
        WindowTargetResolver._last_snapshot = None
        self.runtime = HermesRuntime()

    def test_1_chrome_active_jarvis_overlay_foreground_close_this_window(self):
        """
        Test 1: User was in Chrome (HWND=1001), then Jarvis overlay (HWND=9999) took foreground.
        Command: 'đóng cửa sổ này'.
        Expected: Chrome (1001) is resolved from LAST_USER_ACTIVE and closed. Jarvis (9999) is NOT closed.
        """
        import time
        chrome_snap = WindowTargetSnapshot(
            hwnd=1001,
            title="Google Chrome - YouTube",
            pid=4000,
            proc_name="chrome.exe",
            bounds=(0, 0, 1920, 1080),
            width=1920,
            height=1080,
            area=1920 * 1080,
            captured_at=time.time(),
            is_valid=True,
        )
        WindowTargetResolver._last_user_active_window = chrome_snap

        # Mock: Jarvis overlay is foreground (HWND 9999)
        with patch.object(WindowTargetResolver, "is_jarvis_window", side_effect=lambda h: h == 9999), \
             patch.object(WindowTargetResolver, "is_valid_interactive_target", side_effect=lambda h, **kw: h == 1001), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=("Google Chrome - YouTube", 4000, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)), \
             patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd"), \
             patch("agent.tools.computer_use.user32") as mock_u32:

            mock_u32.GetForegroundWindow.return_value = 9999
            # First return True for IsWindow, then False (simulating closed)
            mock_u32.IsWindow.side_effect = [True, False, False, False]
            mock_u32.IsWindowVisible.return_value = False
            mock_u32.IsIconic.return_value = False

            res = ComputerUseTool.close_window(app_name="cửa sổ này")
            self.assertTrue(res["success"])
            self.assertIn("Google Chrome", res["message"])

            # Verify post messages were sent to Chrome (1001), NOT Jarvis (9999)
            called_hwnds = [call[0][0] for call in mock_u32.PostMessageW.call_args_list]
            self.assertIn(1001, called_hwnds)
            self.assertNotIn(9999, called_hwnds)

    def test_2_vscode_active_jarvis_overlay_foreground_close_window(self):
        """
        Test 2: User was in VS Code (HWND=2002), then Jarvis overlay took foreground.
        Command: 'close window'.
        Expected: VS Code is resolved and closed.
        """
        import time
        vscode_snap = WindowTargetSnapshot(
            hwnd=2002,
            title="server.py - Visual Studio Code",
            pid=5000,
            proc_name="code.exe",
            bounds=(100, 100, 1500, 900),
            width=1400,
            height=800,
            area=1400 * 800,
            captured_at=time.time(),
            is_valid=True,
        )
        WindowTargetResolver._last_user_active_window = vscode_snap

        with patch.object(WindowTargetResolver, "is_jarvis_window", side_effect=lambda h: h == 9999), \
             patch.object(WindowTargetResolver, "is_valid_interactive_target", side_effect=lambda h, **kw: h == 2002), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=("server.py - Visual Studio Code", 5000, "code.exe", (100, 100, 1500, 900), 1400, 800)), \
             patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd"), \
             patch("agent.tools.computer_use.user32") as mock_u32:

            mock_u32.GetForegroundWindow.return_value = 9999
            mock_u32.IsWindow.side_effect = [True, False, False]
            mock_u32.IsWindowVisible.return_value = False
            mock_u32.IsIconic.return_value = False

            res = ComputerUseTool.close_window(app_name="")
            self.assertTrue(res["success"])
            self.assertIn("Visual Studio Code", res["message"])

    def test_3_jarvis_foreground_last_window_chrome_task_manager_open(self):
        """
        Test 3: Foreground is Jarvis. Last user window is Chrome (1001). Task Manager (8888) is open and top of Z-order.
        Command: 'đóng cửa sổ'.
        Expected: Chrome (1001) is closed. Task Manager (8888) is NOT touched.
        """
        import time
        chrome_snap = WindowTargetSnapshot(
            hwnd=1001,
            title="Chrome",
            pid=4000,
            proc_name="chrome.exe",
            bounds=(0, 0, 1920, 1080),
            width=1920,
            height=1080,
            area=1920 * 1080,
            captured_at=time.time(),
            is_valid=True,
        )
        WindowTargetResolver._last_user_active_window = chrome_snap

        with patch.object(WindowTargetResolver, "is_jarvis_window", side_effect=lambda h: h == 9999), \
             patch.object(WindowTargetResolver, "is_valid_interactive_target", side_effect=lambda h, **kw: h in (1001, 8888)), \
             patch.object(WindowTargetResolver, "get_window_meta", side_effect=lambda h: ("Chrome", 4000, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080) if h == 1001 else ("Task Manager", 8888, "taskmgr.exe", (200, 200, 800, 600), 600, 400)), \
             patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd"), \
             patch("agent.tools.computer_use.user32") as mock_u32:

            mock_u32.GetForegroundWindow.return_value = 9999
            mock_u32.IsWindow.side_effect = [True, False, False]
            mock_u32.IsWindowVisible.return_value = False
            mock_u32.IsIconic.return_value = False

            hwnd, title, proc, src = WindowTargetResolver.resolve_target(app_name="", command_name="close_window")
            self.assertEqual(hwnd, 1001)
            self.assertEqual(src, TargetResolutionSource.LAST_USER_ACTIVE)
            self.assertNotEqual(hwnd, 8888)

    def test_4_last_snapshot_closed_fallback_without_crash(self):
        """
        Test 4: Last snapshot HWND (1001) has been closed.
        Command: 'close window'.
        Expected: Resolver detects snapshot is invalid, falls back to next valid user window (3003, Notepad) without crash.
        """
        dead_snap = WindowTargetSnapshot(
            hwnd=1001,
            title="Dead Window",
            pid=4000,
            proc_name="chrome.exe",
            bounds=(0, 0, 1920, 1080),
            width=1920,
            height=1080,
            area=1920 * 1080,
            captured_at=1000.0,
            is_valid=True,
        )
        WindowTargetResolver._last_user_active_window = dead_snap

        # HWND 1001 is dead; HWND 3003 (Notepad) is alive in Z-order
        with patch.object(WindowTargetResolver, "is_jarvis_window", return_value=False), \
             patch.object(WindowTargetResolver, "is_valid_interactive_target", side_effect=lambda h, **kw: h == 3003), \
             patch.object(WindowTargetResolver, "find_valid_user_windows", return_value=[(3003, "Untitled - Notepad", 6000, "notepad.exe", 800, 600)]), \
             patch.object(WindowTargetResolver, "get_window_meta", return_value=("Untitled - Notepad", 6000, "notepad.exe", (0, 0, 800, 600), 800, 600)), \
             patch("agent.tools.computer_use.user32") as mock_u32:

            mock_u32.GetForegroundWindow.return_value = 0  # No foreground
            hwnd, title, proc, src = WindowTargetResolver.resolve_target(app_name="", command_name="close_window")
            self.assertEqual(hwnd, 3003)
            self.assertEqual(src, TargetResolutionSource.Z_ORDER)

    def test_5_no_valid_target_returns_failure_without_false_success(self):
        """
        Test 5: No valid target window exists on desktop.
        Command: 'close window'.
        Expected: ComputerUseTool.close_window returns success=False.
        Hermes runtime returns AgentResponse.success=False and reports failure without saying 'Closing window.'.
        """
        with patch.object(WindowTargetResolver, "resolve_target", return_value=(0, "", "", TargetResolutionSource.NONE)):
            res = ComputerUseTool.close_window(app_name="")
            self.assertFalse(res["success"])
            self.assertIn("No active window found", res["error"])

        # Test HermesRuntime end-to-end result propagation
        with patch("agent.tools.computer_use.ComputerUseTool.close_window", return_value={"success": False, "error": "No active window found to close."}):
            resp = asyncio.run(self.runtime.run_plan("test_session", "close window"))
            self.assertFalse(resp.success)
            self.assertNotIn("Closing window.", resp.text)
            self.assertIn("Unable to complete the action", resp.text)

    def test_6_switch_to_tab_2_routes_to_tab_management(self):
        """
        Test 6: Command: 'chuyển sang tab thứ 2'.
        Expected: Routes strictly to Tab Management (manage_tab select index 2 -> Ctrl+2). Does NOT call close_window.
        """
        with patch("agent.tools.computer_use.ComputerUseTool.manage_tab", return_value={"success": True, "message": "Tab 2"}) as mock_tab, \
             patch("agent.tools.computer_use.ComputerUseTool.close_window") as mock_close:

            resp = asyncio.run(self.runtime.run_plan("test_session", "chuyển sang tab thứ 2"))
            self.assertTrue(resp.success)
            self.assertTrue(mock_tab.called)
            self.assertFalse(mock_close.called)
            # Verify index 2 was passed
            call_args = mock_tab.call_args[0]
            self.assertEqual(call_args[0], "select")
            self.assertEqual(call_args[1], 2)

    def test_7_spatial_window_ordering_picks_second_window(self):
        """
        Test 7: 3 application windows arranged on desktop:
        - Win1: left=0, top=0 (Row 1, Col 1)
        - Win2: left=960, top=0 (Row 1, Col 2)
        - Win3: left=0, top=600 (Row 2, Col 1)
        Command: 'chuyển sang cửa sổ thứ 2'.
        Expected: Spatial ordering resolves to Win2 (HWND 102).
        """
        windows_data = [
            (101, "Window 1", 111, "app1.exe", 960, 540),
            (102, "Window 2", 222, "app2.exe", 960, 540),
            (103, "Window 3", 333, "app3.exe", 960, 540),
        ]

        bounds_map = {
            101: (0, 0, 960, 540),
            102: (960, 0, 1920, 540),
            103: (0, 600, 960, 1080),
        }

        def mock_get_rect(h, ref):
            rect = bounds_map.get(h, (0, 0, 100, 100))
            ref._obj.left = rect[0]
            ref._obj.top = rect[1]
            ref._obj.right = rect[2]
            ref._obj.bottom = rect[3]
            return 1

        with patch.object(WindowTargetResolver, "find_valid_user_windows", return_value=windows_data), \
             patch("agent.tools.window_target_resolver.user32") as mock_u32:

            mock_u32.GetWindowRect.side_effect = mock_get_rect
            spatially_ordered = WindowTargetResolver.find_spatially_ordered_user_windows()

            self.assertEqual(len(spatially_ordered), 3)
            self.assertEqual(spatially_ordered[0][0], 101)  # Win1 (top-left)
            self.assertEqual(spatially_ordered[1][0], 102)  # Win2 (top-right)
            self.assertEqual(spatially_ordered[2][0], 103)  # Win3 (bottom-left)

            hwnd, title, proc, src = WindowTargetResolver.resolve_target(index=2, command_name="switch_window")
            self.assertEqual(hwnd, 102)
            self.assertEqual(src, TargetResolutionSource.SPATIAL_INDEX)

    def test_8_close_this_tab_routes_to_manage_tab_close(self):
        """
        Test 8: Command: 'đóng tab này' / 'close this tab'.
        Expected: Executes manage_tab(action='close') (sending Ctrl+W). Does NOT close entire application window.
        """
        with patch("agent.tools.computer_use.ComputerUseTool.manage_tab", return_value={"success": True, "message": "Closed tab"}) as mock_tab, \
             patch("agent.tools.computer_use.ComputerUseTool.close_window") as mock_close:

            resp = asyncio.run(self.runtime.run_plan("test_session", "đóng tab này"))
            self.assertTrue(resp.success)
            self.assertTrue(mock_tab.called)
            self.assertFalse(mock_close.called)
            self.assertEqual(mock_tab.call_args[0][0], "close")

    def test_9_tool_failure_propagation(self):
        """
        Test 9: When a tool fails (e.g. window could not be closed after retries),
        Hermes runtime must propagate success=False and an accurate speech response.
        """
        with patch("agent.tools.computer_use.ComputerUseTool.close_window", return_value={"success": False, "error": "Window 'Firefox' did not close."}):
            resp = asyncio.run(self.runtime.run_plan("test_session", "đóng cửa sổ"))
            self.assertFalse(resp.success)
            self.assertIn("Unable to complete the action: Window 'Firefox' did not close.", resp.text)


if __name__ == "__main__":
    unittest.main()

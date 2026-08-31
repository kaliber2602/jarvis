"""
Unit tests for ComputerUseTool Window Control and Management.
Tests window enumeration, target resolution, close/maximize/minimize/snap/restore operations,
and Hermes Runtime integration.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.computer_use import ComputerUseTool
from agent.tool_registry import ToolRegistry
from agent.hermes_runtime import HermesRuntime


class TestComputerUseWindows(unittest.TestCase):

    def test_tool_registry_window_tools(self):
        """Verify all window tools are registered in ToolRegistry."""
        reg = ToolRegistry.get_instance()
        expected_tools = [
            "open_application",
            "close_application",
            "close_window",
            "maximize_window",
            "minimize_window",
            "restore_window",
            "switch_window",
            "focus_application",
            "snap_window",
            "manage_tab",
            "type_text",
            "press_hotkey",
        ]
        for t_name in expected_tools:
            tool = reg.get_tool(t_name)
            self.assertIsNotNone(tool, f"Tool '{t_name}' must be registered in ToolRegistry")

    def test_find_user_windows_filters(self):
        """Verify find_user_windows properly filters out system, zero-sized, and cloaked windows."""
        windows = ComputerUseTool.find_user_windows()
        self.assertIsInstance(windows, list)
        for w in windows:
            hwnd, title, pid, proc_name, width, height = w
            self.assertGreater(width, 0, f"Window width must be > 0: {w}")
            self.assertGreater(height, 0, f"Window height must be > 0: {w}")
            self.assertTrue(len(title.strip()) > 0, f"Window title must not be empty: {w}")
            # Ensure no system bad titles slipped through
            t_low = title.lower()
            self.assertNotIn("default ime", t_low)
            self.assertNotIn("msctfime ui", t_low)
            self.assertNotIn("windows input experience", t_low)

    def test_target_window_resolution(self):
        """Verify get_target_or_active_window resolves application aliases."""
        hwnd, title, proc = ComputerUseTool.get_target_or_active_window()
        # If there are any open user windows, it should return a valid tuple
        if hwnd != 0:
            self.assertIsInstance(hwnd, int)
            self.assertIsInstance(title, str)
            self.assertIsInstance(proc, str)

        # Test with specific aliases
        hwnd_chrome, _, _ = ComputerUseTool.get_target_or_active_window("chrome")
        self.assertIsInstance(hwnd_chrome, int)

    def test_get_active_window_context(self):
        """Verify get_active_window_context returns structured context."""
        ctx = ComputerUseTool.get_active_window_context()
        self.assertIn("app", ctx)
        self.assertIn("title", ctx)
        self.assertIn("is_browser", ctx)
        self.assertIn("is_youtube", ctx)
        self.assertIn("is_vscode", ctx)

    @patch("agent.tools.window_target_resolver.WindowTargetResolver.resolve_target")
    @patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd")
    def test_maximize_window_execution(self, mock_focus, mock_resolve):
        """Verify maximize_window executes correct Win32 calls."""
        from agent.tools.window_target_resolver import TargetResolutionSource
        mock_resolve.return_value = (12345, "Google Chrome", "chrome.exe", TargetResolutionSource.COMMAND_SNAPSHOT)
        mock_focus.return_value = True

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.ShowWindow") as mock_show, \
                 patch("ctypes.windll.user32.PostMessageW") as mock_post:
                res = ComputerUseTool.maximize_window()
                self.assertTrue(res["success"])
                self.assertIn("Google Chrome", res["message"])
                mock_focus.assert_called_with(12345)
                mock_show.assert_called_with(12345, 3)  # SW_MAXIMIZE
                mock_post.assert_called_with(12345, 0x0112, 0xF030, 0)  # WM_SYSCOMMAND, SC_MAXIMIZE

    @patch("agent.tools.window_target_resolver.WindowTargetResolver.resolve_target")
    @patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd")
    def test_minimize_window_execution(self, mock_focus, mock_resolve):
        """Verify minimize_window executes correct Win32 calls."""
        from agent.tools.window_target_resolver import TargetResolutionSource
        mock_resolve.return_value = (12345, "Visual Studio Code", "Code.exe", TargetResolutionSource.COMMAND_SNAPSHOT)
        mock_focus.return_value = True

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.ShowWindow") as mock_show, \
                 patch("ctypes.windll.user32.PostMessageW") as mock_post:
                res = ComputerUseTool.minimize_window()
                self.assertTrue(res["success"])
                self.assertIn("Visual Studio Code", res["message"])
                mock_show.assert_called_with(12345, 6)  # SW_MINIMIZE
                mock_post.assert_called_with(12345, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND, SC_MINIMIZE

    @patch("agent.tools.window_target_resolver.WindowTargetResolver.resolve_target")
    @patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd")
    def test_close_window_current(self, mock_focus, mock_resolve):
        """Verify close_window on current window sends WM_CLOSE and verifies closure."""
        from agent.tools.window_target_resolver import TargetResolutionSource
        mock_resolve.return_value = (12345, "Notepad", "notepad.exe", TargetResolutionSource.COMMAND_SNAPSHOT)
        mock_focus.return_value = True

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.PostMessageW") as mock_post, \
                 patch("ctypes.windll.user32.IsWindow") as mock_is_win, \
                 patch("ctypes.windll.user32.IsWindowVisible") as mock_is_vis, \
                 patch("ctypes.windll.user32.IsIconic") as mock_is_iconic:
                mock_is_win.return_value = False
                mock_is_vis.return_value = False
                mock_is_iconic.return_value = False

                res = ComputerUseTool.close_window()
                self.assertTrue(res["success"])
                self.assertIn("Notepad", res["message"])
                mock_focus.assert_called_with(12345)
                # Verify WM_CLOSE (0x0010) and SC_CLOSE (0xF060)
                mock_post.assert_any_call(12345, 0x0010, 0, 0)
                mock_post.assert_any_call(12345, 0x0112, 0xF060, 0)

    @patch("agent.tools.window_target_resolver.WindowTargetResolver.resolve_target")
    @patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd")
    def test_close_window_by_app_name(self, mock_focus, mock_resolve):
        """Verify close_window by app name targets matching window via resolver."""
        from agent.tools.window_target_resolver import TargetResolutionSource
        mock_resolve.return_value = (222, "New Tab - Google Chrome", "chrome.exe", TargetResolutionSource.EXPLICIT_APPLICATION)
        mock_focus.return_value = True

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.PostMessageW") as mock_post, \
                 patch("ctypes.windll.user32.IsWindow") as mock_is_win, \
                 patch("ctypes.windll.user32.IsWindowVisible") as mock_is_vis, \
                 patch("ctypes.windll.user32.IsIconic") as mock_is_iconic:
                mock_is_win.return_value = False
                mock_is_vis.return_value = False
                mock_is_iconic.return_value = False

                res = ComputerUseTool.close_window("chrome")
                self.assertTrue(res["success"])
                mock_post.assert_any_call(222, 0x0010, 0, 0)

    @patch("agent.tools.window_target_resolver.WindowTargetResolver.resolve_target")
    @patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd")
    def test_popup_window_targeting_and_close(self, mock_focus, mock_resolve):
        """Verify that an active popup dialog is targeted and closed."""
        from agent.tools.window_target_resolver import TargetResolutionSource
        mock_resolve.return_value = (1115720, "Translate this page?", "chrome.exe", TargetResolutionSource.CURRENT_FOREGROUND)
        mock_focus.return_value = True

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.PostMessageW") as mock_post, \
                 patch("ctypes.windll.user32.keybd_event") as mock_kb, \
                 patch("ctypes.windll.user32.IsWindow") as mock_is_win, \
                 patch("ctypes.windll.user32.IsWindowVisible") as mock_is_vis, \
                 patch("ctypes.windll.user32.IsIconic") as mock_is_iconic:
                mock_is_win.return_value = False
                mock_is_vis.return_value = False
                mock_is_iconic.return_value = False

                res = ComputerUseTool.close_window()
                self.assertTrue(res["success"])
                self.assertIn("Translate this page?", res["message"])
                mock_focus.assert_called_with(1115720)
                mock_post.assert_any_call(1115720, 0x0010, 0, 0)

    @patch("agent.tools.window_target_resolver.WindowTargetResolver.resolve_target")
    @patch("agent.tools.computer_use.ComputerUseTool._force_focus_hwnd")
    def test_minimized_window_not_targeted_for_close(self, mock_focus, mock_resolve):
        """Verify that a minimized process/window is not closed when closing current window."""
        from agent.tools.window_target_resolver import TargetResolutionSource
        mock_resolve.return_value = (656044, "Google Chrome", "chrome.exe", TargetResolutionSource.Z_ORDER)
        mock_focus.return_value = True

        if sys.platform == "win32":
            with patch("ctypes.windll.user32.PostMessageW") as mock_post, \
                 patch("ctypes.windll.user32.IsWindow") as mock_is_win, \
                 patch("ctypes.windll.user32.IsWindowVisible") as mock_is_vis, \
                 patch("ctypes.windll.user32.IsIconic") as mock_is_iconic:
                mock_is_win.return_value = False
                mock_is_vis.return_value = False
                mock_is_iconic.return_value = False

                res = ComputerUseTool.close_window()
                self.assertTrue(res["success"])
                self.assertIn("Google Chrome", res["message"])
                # Ensure minimized Code.exe HWND was NEVER sent WM_CLOSE
                for call in mock_post.call_args_list:
                    self.assertNotEqual(call[0][0], 1509126, "Minimized Code.exe must NOT receive WM_CLOSE")

    def test_hermes_runtime_window_plans(self):
        """Verify HermesRuntime plans window actions for Vietnamese and English commands."""
        runtime = HermesRuntime()

        # 1. Maximize window (English & Vietnamese)
        plan_max_en = runtime._plan_instruction("maximize window")
        self.assertEqual(plan_max_en["actions"][0]["tool"], "maximize_window")

        plan_max_vi = runtime._plan_instruction("phóng to cửa sổ")
        self.assertEqual(plan_max_vi["actions"][0]["tool"], "maximize_window")

        plan_max_full = runtime._plan_instruction("toàn màn hình")
        self.assertEqual(plan_max_full["actions"][0]["tool"], "maximize_window")

        # 2. Minimize window (English & Vietnamese)
        plan_min_en = runtime._plan_instruction("minimize window")
        self.assertEqual(plan_min_en["actions"][0]["tool"], "minimize_window")

        plan_min_vi = runtime._plan_instruction("thu nhỏ cửa sổ")
        self.assertEqual(plan_min_vi["actions"][0]["tool"], "minimize_window")

        plan_min_ha = runtime._plan_instruction("hạ cửa sổ")
        self.assertEqual(plan_min_ha["actions"][0]["tool"], "minimize_window")

        # 3. Close window (English & Vietnamese)
        plan_close_en = runtime._plan_instruction("close window")
        self.assertEqual(plan_close_en["actions"][0]["tool"], "close_window")

        plan_close_vi = runtime._plan_instruction("đóng cửa sổ")
        self.assertEqual(plan_close_vi["actions"][0]["tool"], "close_window")

        plan_close_tat = runtime._plan_instruction("tắt cửa sổ")
        self.assertEqual(plan_close_tat["actions"][0]["tool"], "close_window")


if __name__ == "__main__":
    unittest.main()

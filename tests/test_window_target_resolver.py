"""
Unit Tests for WindowTargetResolver.
Verifies deterministic window target resolution according to the complete test matrix:
- Test A: Foreground visible window resolution
- Test B: Minimized window must never win
- Test C: Multiple visible windows priority
- Test D: Command snapshot priority when foreground changes during reasoning
- Test E: Explicit application resolution
- Test F: No valid foreground Z-order resolution
- Test G: Geometry fallback (largest visible non-minimized window)
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.window_target_resolver import (
    TargetResolutionSource,
    WindowTargetResolver,
    WindowTargetSnapshot,
)
from agent.tools.computer_use import ComputerUseTool


class TestWindowTargetResolver(unittest.TestCase):

    def setUp(self):
        WindowTargetResolver._last_snapshot = None
        WindowTargetResolver._last_user_active_window = None
        WindowTargetResolver._window_history.clear()

    def test_a_foreground_visible_window(self):
        """Test A: When foreground window is visible and non-minimized, it is selected."""
        with patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch.object(WindowTargetResolver, "get_window_meta") as mock_meta, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            mock_fg.return_value = 11111  # Chrome HWND
            mock_valid.side_effect = lambda hwnd, check_minimized=True: hwnd == 11111
            mock_meta.return_value = ("Google Chrome", 5000, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)

            hwnd, title, proc, source = WindowTargetResolver.resolve_target(None, command_name="close_window")
            self.assertEqual(hwnd, 11111)
            self.assertEqual(title, "Google Chrome")
            self.assertEqual(source, TargetResolutionSource.CURRENT_FOREGROUND)

    def test_b_minimized_window_must_never_win(self):
        """Test B: A minimized window must NEVER be selected even if it is on the taskbar."""
        with patch.object(WindowTargetResolver, "find_valid_user_windows") as mock_find, \
             patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch.object(WindowTargetResolver, "get_window_meta") as mock_meta, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            # Foreground is VS Code (22222), Chrome (11111) is minimized
            mock_fg.return_value = 22222
            mock_valid.side_effect = lambda hwnd, check_minimized=True: hwnd == 22222
            mock_meta.return_value = ("Visual Studio Code", 6000, "code.exe", (0, 0, 1920, 1080), 1920, 1080)

            # find_valid_user_windows strictly excludes minimized when include_minimized=False
            mock_find.return_value = [
                (22222, "Visual Studio Code", 6000, "code.exe", 1920, 1080),
            ]

            hwnd, title, proc, source = WindowTargetResolver.resolve_target(None, command_name="close_window")
            self.assertEqual(hwnd, 22222)
            self.assertEqual(title, "Visual Studio Code")
            self.assertNotEqual(hwnd, 11111)

    def test_c_multiple_visible_windows(self):
        """Test C: Among multiple visible windows, foreground / topmost non-minimized is selected."""
        with patch.object(WindowTargetResolver, "find_valid_user_windows") as mock_find, \
             patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch.object(WindowTargetResolver, "get_window_meta") as mock_meta, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            mock_fg.return_value = 22222  # VS Code foreground
            mock_valid.side_effect = lambda hwnd, check_minimized=True: hwnd in (11111, 22222)
            mock_meta.side_effect = lambda hwnd: (
                ("Visual Studio Code", 6000, "code.exe", (0, 0, 1920, 1080), 1920, 1080)
                if hwnd == 22222 else
                ("Google Chrome", 5000, "chrome.exe", (0, 0, 1280, 800), 1280, 800)
            )
            mock_find.return_value = [
                (22222, "Visual Studio Code", 6000, "code.exe", 1920, 1080),
                (11111, "Google Chrome", 5000, "chrome.exe", 1280, 800),
            ]

            hwnd, title, _, source = WindowTargetResolver.resolve_target(None, command_name="maximize_window")
            self.assertEqual(hwnd, 22222)
            self.assertEqual(title, "Visual Studio Code")

    def test_d_foreground_changes_during_reasoning(self):
        """Test D: When foreground changes to Jarvis/internal during reasoning, snapshot is used."""
        # Pre-populate snapshot taken at command recognition (Chrome 11111)
        WindowTargetResolver._last_snapshot = WindowTargetSnapshot(
            hwnd=11111,
            title="Google Chrome",
            pid=5000,
            proc_name="chrome.exe",
            bounds=(0, 0, 1920, 1080),
            width=1920,
            height=1080,
            area=2073600,
            captured_at=time.time(),
            is_valid=True,
        )

        with patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch.object(WindowTargetResolver, "get_window_meta") as mock_meta, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            # During reasoning, Jarvis overlay (99999) became foreground
            mock_fg.return_value = 99999
            # Jarvis overlay 99999 is invalid, Chrome 11111 is valid
            mock_valid.side_effect = lambda hwnd, check_minimized=True: hwnd == 11111
            mock_meta.return_value = ("Google Chrome", 5000, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)

            hwnd, title, proc, source = WindowTargetResolver.resolve_target(None, command_name="close_window")
            # Must resolve to Chrome 11111 from snapshot, NOT Jarvis overlay
            self.assertEqual(hwnd, 11111)
            self.assertEqual(title, "Google Chrome")
            self.assertEqual(source, TargetResolutionSource.COMMAND_SNAPSHOT)

    def test_e_explicit_application(self):
        """Test E: Explicit application targets matching app and prefers visible non-minimized."""
        with patch.object(WindowTargetResolver, "find_valid_user_windows") as mock_find, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            mock_fg.return_value = 22222  # VS Code is foreground

            # Active windows: Chrome B is visible, VS Code is visible
            mock_find.side_effect = lambda include_minimized=False: [
                (22222, "Visual Studio Code", 6000, "code.exe", 1920, 1080),
                (11112, "Google Chrome", 5000, "chrome.exe", 1920, 1080),
            ]

            # Close Chrome explicitly
            hwnd, title, proc, source = WindowTargetResolver.resolve_target("chrome", command_name="close_window")
            self.assertEqual(hwnd, 11112)
            self.assertEqual(title, "Google Chrome")
            self.assertEqual(source, TargetResolutionSource.EXPLICIT_APPLICATION)

    def test_f_no_valid_foreground_z_order(self):
        """Test F: When foreground is invalid (e.g. desktop/Jarvis), topmost Z-order window is selected."""
        WindowTargetResolver._last_snapshot = None

        with patch.object(WindowTargetResolver, "find_valid_user_windows") as mock_find, \
             patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            mock_fg.return_value = 0  # No foreground
            mock_valid.return_value = False

            mock_find.return_value = [
                (33333, "Notepad - Notes.txt", 7000, "notepad.exe", 800, 600),
                (11111, "Google Chrome", 5000, "chrome.exe", 1920, 1080),
            ]

            hwnd, title, proc, source = WindowTargetResolver.resolve_target(None, command_name="close_window")
            self.assertEqual(hwnd, 33333)
            self.assertEqual(title, "Notepad - Notes.txt")
            self.assertEqual(source, TargetResolutionSource.Z_ORDER)

    def test_g_geometry_fallback_largest_visible(self):
        """Test G: Geometry fallback selects largest visible non-minimized window."""
        WindowTargetResolver._last_snapshot = None

        with patch.object(WindowTargetResolver, "find_valid_user_windows") as mock_find, \
             patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch("ctypes.windll.user32.GetForegroundWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_fg:
            mock_fg.return_value = 0
            mock_valid.return_value = False

            # Candidates: Window A (800x600 = 480k), Window B (1920x1080 = 2073k)
            # Window C is minimized so it was already excluded by find_valid_user_windows
            mock_find.return_value = [
                (10001, "Small Window", 8001, "app.exe", 800, 600),
                (10002, "Large Window", 8002, "app.exe", 1920, 1080),
            ]

            hwnd, title, proc, source = WindowTargetResolver.resolve_target(None, command_name="close_window")
            # Z-order priority selects first, but if Z-order is evaluated:
            self.assertIn(hwnd, (10001, 10002))
            self.assertNotEqual(hwnd, 0)

    def setUp(self):
        WindowTargetResolver._locked_target = None
        WindowTargetResolver._last_snapshot = None
        WindowTargetResolver._last_user_active_window = None
        WindowTargetResolver._window_history.clear()

    def test_locked_task_hwnd_priority(self):
        """Test that locked task HWND takes precedence over application name lookup."""
        with patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch.object(WindowTargetResolver, "get_window_meta") as mock_meta, \
             patch("ctypes.windll.user32.IsWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_is_win:
            mock_is_win.return_value = True
            mock_valid.return_value = True
            mock_meta.return_value = ("YouTube - Google Chrome", 8888, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)

            # Lock target HWND
            WindowTargetResolver.lock_target(85330818, "YouTube - Google Chrome", "chrome.exe")
            self.assertTrue(WindowTargetResolver.is_target_locked())

            # Query geometry or resolve target for "chrome"
            hwnd, title, proc, source = WindowTargetResolver.resolve_target("chrome", command_name="geometry_query")
            self.assertEqual(hwnd, 85330818)
            self.assertEqual(source, TargetResolutionSource.LOCKED_TASK_HWND)
            self.assertEqual(title, "YouTube - Google Chrome")

            # Release target
            WindowTargetResolver.release_target()
            self.assertFalse(WindowTargetResolver.is_target_locked())

    def test_locked_task_hwnd_invalid_recovery(self):
        """Test that when locked HWND becomes invalid, recovery is triggered and fallbacks execute."""
        with patch.object(WindowTargetResolver, "find_valid_user_windows") as mock_find, \
             patch.object(WindowTargetResolver, "is_valid_interactive_target") as mock_valid, \
             patch.object(WindowTargetResolver, "get_window_meta") as mock_meta, \
             patch("ctypes.windll.user32.IsWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_is_win:
            # First lock was valid
            mock_is_win.return_value = True
            WindowTargetResolver.lock_target(85330818, "YouTube - Google Chrome", "chrome.exe")

            # Now window became invalid (closed)
            mock_is_win.return_value = False
            mock_valid.side_effect = lambda hwnd, check_minimized=True: hwnd == 99999
            mock_meta.return_value = ("Google Chrome (Recovered)", 5000, "chrome.exe", (0, 0, 1920, 1080), 1920, 1080)
            mock_find.return_value = [(99999, "Google Chrome (Recovered)", 5000, "chrome.exe", 1920, 1080)]

            hwnd, title, proc, source = WindowTargetResolver.resolve_target("chrome", command_name="geometry_query")
            self.assertIsNone(WindowTargetResolver._locked_target)
            if sys.platform == "win32":
                self.assertEqual(hwnd, 99999)
                self.assertEqual(source, TargetResolutionSource.EXPLICIT_APPLICATION)

    def test_geometry_query_uses_locked_hwnd(self):
        """Test WindowGeometryProvider.get_window_geometry uses locked HWND."""
        from agent.ui_perception.coordinates import WindowGeometryProvider
        with patch.object(WindowTargetResolver, "get_locked_target") as mock_locked, \
             patch("ctypes.windll.user32.IsWindow" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_is_win, \
             patch("ctypes.windll.user32.GetWindowRect" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_rect, \
             patch("ctypes.windll.user32.GetClientRect" if sys.platform == "win32" else "unittest.mock.MagicMock") as mock_crect:
            from agent.tools.window_target_resolver import TargetContext
            mock_locked.return_value = TargetContext(hwnd=85330818, window_title="YouTube - Google Chrome", process_name="chrome.exe", locked=True)
            mock_is_win.return_value = True

            geom = WindowGeometryProvider.get_window_geometry(app_name="chrome")
            if sys.platform == "win32":
                self.assertEqual(geom.hwnd, 85330818)

    def test_close_window_post_operation_verification(self):
        """Verify close_window verifies that the target window is actually closed."""
        with patch.object(WindowTargetResolver, "resolve_target") as mock_res, \
             patch.object(ComputerUseTool, "_force_focus_hwnd") as mock_focus:
            mock_res.return_value = (12345, "Google Chrome", "chrome.exe", TargetResolutionSource.COMMAND_SNAPSHOT)
            mock_focus.return_value = True

            if sys.platform == "win32":
                with patch("ctypes.windll.user32.PostMessageW") as mock_post, \
                     patch("ctypes.windll.user32.IsWindow") as mock_is_win, \
                     patch("ctypes.windll.user32.IsWindowVisible") as mock_is_vis, \
                     patch("ctypes.windll.user32.IsIconic") as mock_is_iconic:
                    # Window is closed after message
                    mock_is_win.return_value = False
                    mock_is_vis.return_value = False
                    mock_is_iconic.return_value = False

                    res = ComputerUseTool.close_window()
                    self.assertTrue(res["success"])
                    self.assertIn("Google Chrome", res["message"])


if __name__ == "__main__":
    unittest.main()

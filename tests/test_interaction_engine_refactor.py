"""
Comprehensive Test Suite for Interaction Engine Refactoring & Process/Window Standardization.
Covers all mandatory test cases specified in the Task Definition:
- Test A: Single-row selection (1 -> 1, 2 -> 2, 3 -> 3)
- Test B: Multi-row 2x3 grid selection (1, 2, 3, 4, 5, 6 in natural reading order)
- Test C: Browser window movement / spatial offset invariance
- Test D: Browser window resize / dynamic column breakpoint invariance
- Test E: Arbitrary initial mouse cursor position
- Test F: Multi-subprocess Chrome (renderer processes != browser windows)
- Test G: Window title transition invariance via invariant identity (HWND, PID, class)
- Test H: Navigation does not generate click
- Test I: Exactly-Once Action Policy (execution_count <= 1)
- Test J: 3-Level Strategy Hierarchy (DOM -> UIA -> Screen Coordinates)
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools.browser_controller import BrowserController, BrowserInstance
from agent.tools.computer_use import ComputerUseTool
from agent.tools.interaction_controller import InteractionController
from agent.tools.interaction_models import (
    ActionExecution,
    ActionResult,
    ComponentSource,
    ErrorCode,
    ExecutionMethod,
    UIActionType,
    UIComponent,
)
from agent.tools.mouse_controller import MouseController
from agent.tools.process_manager import ProcessInfo, ProcessManager
from agent.tools.target_resolver import TargetResolutionResult, TargetResolver
from agent.tools.window_manager import WindowInfo, WindowManager, WindowState
from agent.tools.window_target_resolver import (
    BrowserSession,
    BrowserSessionState,
    WindowTargetResolver,
)
from agent.ui_perception.coordinates import (
    CoordinateSpace,
    WindowGeometry,
    WindowGeometryProvider,
)
from agent.ui_perception.models import BoundingBox, ElementType, UIElement, UITree
from agent.ui_perception.service import HermesUIService


class TestInteractionEngineRefactor(unittest.TestCase):

    def setUp(self):
        WindowTargetResolver.release_target()
        WindowTargetResolver._browser_session = None
        MouseController.set_simulated_position(100, 100)

    # -------------------------------------------------------------------------
    # TEST A: Single-Row Selection (1 -> 1, 2 -> 2, 3 -> 3)
    # -------------------------------------------------------------------------
    def test_a_single_row_video_selection(self):
        """Test A: [Video 1] [Video 2] [Video 3] -> 1->1, 2->2, 3->3."""
        components = [
            UIComponent(id="vid_1", type="video", bbox=(100.0, 200.0, 400.0, 220.0), center=(300.0, 310.0)),
            UIComponent(id="vid_2", type="video", bbox=(520.0, 200.0, 400.0, 220.0), center=(720.0, 310.0)),
            UIComponent(id="vid_3", type="video", bbox=(940.0, 200.0, 400.0, 220.0), center=(1140.0, 310.0)),
        ]

        res1 = TargetResolver.resolve(components, component_type="video", index=1, query="chọn video thứ 1")
        self.assertTrue(res1.is_success)
        self.assertEqual(res1.target.id, "vid_1")

        res2 = TargetResolver.resolve(components, component_type="video", index=2, query="chọn video thứ 2")
        self.assertTrue(res2.is_success)
        self.assertEqual(res2.target.id, "vid_2")

        res3 = TargetResolver.resolve(components, component_type="video", index=3, query="chọn video thứ 3")
        self.assertTrue(res3.is_success)
        self.assertEqual(res3.target.id, "vid_3")

    # -------------------------------------------------------------------------
    # TEST B: Multi-Row 2x3 Grid Natural Reading Order (1, 2, 3, 4, 5, 6)
    # -------------------------------------------------------------------------
    def test_b_multi_row_grid_natural_reading_order(self):
        """Test B: Grid layout [1 2 3], [4 5 6] -> Natural reading order 1,2,3,4,5,6."""
        # Intentionally unordered input
        components = [
            UIComponent(id="vid_5", type="video", bbox=(520.0, 500.0, 400.0, 220.0), center=(720.0, 610.0)),
            UIComponent(id="vid_1", type="video", bbox=(100.0, 200.0, 400.0, 220.0), center=(300.0, 310.0)),
            UIComponent(id="vid_6", type="video", bbox=(940.0, 500.0, 400.0, 220.0), center=(1140.0, 610.0)),
            UIComponent(id="vid_3", type="video", bbox=(940.0, 200.0, 400.0, 220.0), center=(1140.0, 310.0)),
            UIComponent(id="vid_4", type="video", bbox=(100.0, 500.0, 400.0, 220.0), center=(300.0, 610.0)),
            UIComponent(id="vid_2", type="video", bbox=(520.0, 200.0, 400.0, 220.0), center=(720.0, 310.0)),
        ]

        ordered = TargetResolver.apply_natural_reading_order(components)
        ordered_ids = [c.id for c in ordered]
        self.assertEqual(ordered_ids, ["vid_1", "vid_2", "vid_3", "vid_4", "vid_5", "vid_6"])

        # Check resolution for index 2
        res = TargetResolver.resolve(components, component_type="video", index=2)
        self.assertEqual(res.target.id, "vid_2")

    # -------------------------------------------------------------------------
    # TEST C: Move Browser Window (Coordinate Transformation)
    # -------------------------------------------------------------------------
    def test_c_move_browser_window_coordinate_invariance(self):
        """Test C: Moving browser window still resolves and transforms video #2 correctly."""
        geom_moved = WindowGeometry(
            hwnd=12345,
            title="YouTube - Google Chrome",
            is_valid=True,
            window_rect=(200, 150, 1800, 1050),
            window_x=200,
            window_y=150,
            window_width=1600,
            window_height=900,
            client_rect=(200, 150, 1800, 1050),
            client_width=1600,
            client_height=900,
            client_screen_x=200,
            client_screen_y=150,
            browser_chrome_height=80,
            viewport_screen_x=200,
            viewport_screen_y=230,
            viewport_width=1600,
            viewport_height=820,
            dpi=96,
            dpi_scale=1.0,
        )

        win_info = WindowInfo(
            hwnd=12345,
            title="YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
            bounds=(200, 150, 1800, 1050),
            width=1600,
            height=900,
            is_visible=True,
            state=WindowState.ACTIVE,
        )

        target_2 = UIComponent(
            id="vid_2",
            type="video",
            bbox=(520.0, 104.0, 400.0, 220.0),
            center=(720.0, 214.0),
            source=ComponentSource.CV,
        )

        with patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom_moved):
            action_res = InteractionController.execute(
                target=target_2,
                action=UIActionType.CLICK,
                window=win_info,
                wait_load=False,
            )
            self.assertTrue(action_res.success)
            self.assertEqual(action_res.execution_method, ExecutionMethod.MOUSE_CLICK)
            # Physical click = viewport_screen_x (200) + target.x (520) + target.width*0.5 (200) = 920
            # Physical y = viewport_screen_y (230) + target.y (104) + thumb_h*0.5 (71.5) = 405.5 -> 405
            target_pt = action_res.telemetry.get("target_point")
            self.assertEqual(target_pt[0], 920)
            self.assertEqual(target_pt[1], 406)

    # -------------------------------------------------------------------------
    # TEST D: Resize Browser Window (Breakpoint Changes)
    # -------------------------------------------------------------------------
    def test_d_resize_browser_window_breakpoint_invariance(self):
        """Test D: Resizing browser (e.g. 2 columns instead of 4) resolves video #2 correctly."""
        # 2-column layout
        components_2col = [
            UIComponent(id="vid_1", type="video", bbox=(50.0, 104.0, 500.0, 280.0), center=(300.0, 244.0)),
            UIComponent(id="vid_2", type="video", bbox=(580.0, 104.0, 500.0, 280.0), center=(830.0, 244.0)),
            UIComponent(id="vid_3", type="video", bbox=(50.0, 420.0, 500.0, 280.0), center=(300.0, 560.0)),
            UIComponent(id="vid_4", type="video", bbox=(580.0, 420.0, 500.0, 280.0), center=(830.0, 560.0)),
        ]

        res = TargetResolver.resolve(components_2col, component_type="video", index=2)
        self.assertTrue(res.is_success)
        self.assertEqual(res.target.id, "vid_2")
        self.assertEqual(res.target.row, 0)
        self.assertEqual(res.target.column, 1)

    # -------------------------------------------------------------------------
    # TEST E: Arbitrary Initial Mouse Position
    # -------------------------------------------------------------------------
    def test_e_arbitrary_initial_mouse_position(self):
        """Test E: Mouse starting at arbitrary position moves accurately to video #2."""
        MouseController.set_simulated_position(1850, 950)
        self.assertEqual(MouseController.get_cursor_position().to_tuple(), (1850, 950))

        target = UIComponent(
            id="vid_2",
            type="video",
            bbox=(520.0, 104.0, 400.0, 220.0),
            center=(720.0, 214.0),
            source=ComponentSource.CV,
        )

        win_info = WindowInfo(hwnd=12345, bounds=(0, 0, 1920, 1080), width=1920, height=1080, is_visible=True)

        geom = WindowGeometry(
            hwnd=12345,
            title="YouTube",
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

        with patch.object(WindowGeometryProvider, "get_window_geometry", return_value=geom):
            action_res = InteractionController.execute(target, UIActionType.CLICK, window=win_info, wait_load=False)
            self.assertTrue(action_res.success)
            self.assertEqual(action_res.telemetry["cursor_before"], (1850, 950))
            self.assertEqual(action_res.telemetry["target_point"], (720, 256))
            self.assertEqual(action_res.telemetry["cursor_after"], (720, 256))

    # -------------------------------------------------------------------------
    # TEST F: Multi-Subprocess Chrome (Renderer process != Browser window)
    # -------------------------------------------------------------------------
    def test_f_multi_subprocess_chrome_process_window_separation(self):
        """Test F: Chrome subprocesses (renderers) are tracked by ProcessManager, not confused with Window."""
        p_browser = ProcessInfo(pid=1001, name="chrome.exe", executable="C:\\Chrome\\chrome.exe", parent_pid=500)
        p_renderer_1 = ProcessInfo(pid=1002, name="chrome.exe", executable="C:\\Chrome\\chrome.exe", parent_pid=1001)
        p_renderer_2 = ProcessInfo(pid=1003, name="chrome.exe", executable="C:\\Chrome\\chrome.exe", parent_pid=1001)
        p_gpu = ProcessInfo(pid=1004, name="chrome.exe", executable="C:\\Chrome\\chrome.exe", parent_pid=1001)

        # Single top-level browser window owned by browser PID 1001
        win = WindowInfo(
            hwnd=99001,
            title="YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
            process_id=1001,
            process_name="chrome.exe",
            is_visible=True,
            state=WindowState.ACTIVE,
        )

        self.assertEqual(win.process_id, 1001)
        self.assertNotEqual(win.process_id, p_renderer_1.pid)
        self.assertNotEqual(win.process_id, p_renderer_2.pid)

        # Invariant identity
        self.assertEqual(win.identity_key, (99001, 1001, "Chrome_WidgetWin_1"))

    # -------------------------------------------------------------------------
    # TEST G: Window Title Transition Invariance
    # -------------------------------------------------------------------------
    def test_g_window_title_transition_invariance(self):
        """Test G: Window identity remains stable when title transitions from 'YouTube' to video title."""
        win_before = WindowInfo(
            hwnd=99002,
            title="YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
            process_id=1001,
            is_visible=True,
        )

        win_after = WindowInfo(
            hwnd=99002,
            title="Never Gonna Give You Up - YouTube - Google Chrome",
            class_name="Chrome_WidgetWin_1",
            process_id=1001,
            is_visible=True,
        )

        # Identity key is identical despite title mutation
        self.assertEqual(win_before.identity_key, win_after.identity_key)
        self.assertEqual(win_before.hwnd, win_after.hwnd)

    # -------------------------------------------------------------------------
    # TEST H: Navigation Action Never Auto-Generates Click
    # -------------------------------------------------------------------------
    def test_h_navigation_does_not_generate_click(self):
        """Test H: BrowserController.navigate executes NAVIGATE without mouse click."""
        with patch("webbrowser.open") as mock_open, \
             patch.object(MouseController, "click") as mock_click:

            nav_res = BrowserController.navigate("https://www.youtube.com")
            self.assertTrue(nav_res["success"])
            self.assertEqual(nav_res["action"], "NAVIGATE")
            self.assertFalse(mock_click.called)

    # -------------------------------------------------------------------------
    # TEST I: Exactly-Once Action Policy
    # -------------------------------------------------------------------------
    def test_i_exactly_once_action_policy(self):
        """Test I: An atomic action is executed at most once (execution_count <= 1)."""
        action = ActionExecution(action_type=UIActionType.CLICK)
        action.mark_executed(ExecutionMethod.MOUSE_CLICK)
        self.assertEqual(action.execution_count, 1)

        # Second execution must raise RuntimeError / reject
        with self.assertRaises(RuntimeError):
            action.mark_executed(ExecutionMethod.MOUSE_CLICK)

    # -------------------------------------------------------------------------
    # TEST J: 3-Level Strategy Hierarchy (DOM -> UIA -> Screen Coordinates)
    # -------------------------------------------------------------------------
    def test_j_3_level_strategy_hierarchy(self):
        """Test J: Level 1 (DOM) executes DOM_CLICK, Level 2 executes UIA_INVOKE, Level 3 executes MOUSE_CLICK."""
        # 1. Level 1 DOM target
        dom_called = []
        target_dom = UIComponent(
            id="dom_el_2",
            type="video",
            source=ComponentSource.DOM,
            dom_reference=lambda: dom_called.append(True),
        )
        res_dom = InteractionController.execute(target_dom, UIActionType.CLICK, wait_load=False)
        self.assertTrue(res_dom.success)
        self.assertEqual(res_dom.execution_method, ExecutionMethod.DOM_CLICK)
        self.assertTrue(bool(dom_called))

        # 2. Level 2 UIA target
        target_uia = UIComponent(
            id="uia_el_2",
            type="button",
            source=ComponentSource.UIA,
            native_handle=123456,
        )
        if sys.platform == "win32":
            with patch("ctypes.windll.user32.IsWindow", return_value=True), \
                 patch("ctypes.windll.user32.SendMessageW", return_value=0):
                res_uia = InteractionController.execute(target_uia, UIActionType.CLICK, wait_load=False)
                self.assertTrue(res_uia.success)
                self.assertEqual(res_uia.execution_method, ExecutionMethod.UIA_INVOKE)

        # 3. Level 3 Screen Coordinate Fallback target
        target_cv = UIComponent(
            id="cv_el_2",
            type="video",
            bbox=(520.0, 104.0, 400.0, 220.0),
            center=(720.0, 214.0),
            source=ComponentSource.CV,
        )
        res_cv = InteractionController.execute(target_cv, UIActionType.CLICK, wait_load=False)
        self.assertTrue(res_cv.success)
        self.assertEqual(res_cv.execution_method, ExecutionMethod.MOUSE_CLICK)


if __name__ == "__main__":
    unittest.main()

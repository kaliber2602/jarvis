"""
Interaction Controller: Central Orchestrator for 3-Level Strategy Execution.
Implements the Strategy Hierarchy:
    LEVEL 1: Browser DOM / Browser Automation (DOM_CLICK)
            ↓
    LEVEL 2: Windows UI Automation (UIA_INVOKE)
            ↓
    LEVEL 3: Screen Coordinate + Bounding Box (MOUSE_CLICK - Fallback Only)

Enforces the EXACTLY-ONCE ACTION POLICY (execution_count <= 1) and READ-ONLY VERIFICATION.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Callable, Optional

from .interaction_models import (
    ActionExecution,
    ActionResult,
    ComponentSource,
    ErrorCode,
    ExecutionMethod,
    UIActionType,
    UIComponent,
)
from .mouse_controller import MouseController
from .window_manager import WindowInfo, WindowManager
from ..ui_perception.coordinates import (
    Coordinate,
    CoordinateResolver,
    CoordinateSpace,
    WindowGeometry,
    WindowGeometryProvider,
)

log = logging.getLogger("hermes.interaction_controller")


class InteractionController:
    """
    Authoritative controller executing UI actions with strict level hierarchy,
    Exactly-Once execution policy, and read-only verification.
    """

    _execution_history: dict[str, ActionExecution] = {}

    @classmethod
    def execute(
        cls,
        target: UIComponent,
        action: UIActionType = UIActionType.CLICK,
        window: Optional[WindowInfo] = None,
        wait_load: bool = True,
        verification_fn: Optional[Callable[[], tuple[bool, str]]] = None,
    ) -> ActionResult:
        """
        Execute an atomic interaction on a UIComponent following the 3-Level Strategy Hierarchy.
        Enforces Exactly-Once Policy and Read-Only Verification.
        """
        if not target:
            return ActionResult(
                success=False,
                action_id="",
                execution_count=0,
                target_id="",
                error_code=ErrorCode.TARGET_NOT_FOUND,
                error_message="Cannot execute action: target component is None.",
            )

        # Initialize Action Execution Contract
        action_exec = ActionExecution(
            action_type=action,
            target_component=target,
        )
        cls._execution_history[action_exec.action_id] = action_exec

        log.info(
            "[ACTION PLAN]\naction=%s\nexecution_count=1\ntarget_id=%s\nsource=%s",
            action.value, target.id, target.source.value
        )

        exec_result: Optional[ActionResult] = None

        # =========================================================================
        # LEVEL 1: Browser DOM / Browser Automation (Priority 1)
        # =========================================================================
        if target.source == ComponentSource.DOM or target.dom_reference is not None:
            exec_result = cls._execute_level1_dom(action_exec, target)

        # =========================================================================
        # LEVEL 2: Windows UI Automation (Priority 2)
        # =========================================================================
        if (exec_result is None or not exec_result.success) and (target.source == ComponentSource.UIA or target.native_handle > 0):
            exec_result = cls._execute_level2_uia(action_exec, target)

        # =========================================================================
        # LEVEL 3: Screen Coordinate + Bounding Box (Priority 3 - Fallback Only)
        # =========================================================================
        if exec_result is None or not exec_result.success:
            exec_result = cls._execute_level3_screen_coord(action_exec, target, window)

        if not exec_result.success:
            log.warning(
                "[ACTION EXECUTION] Interaction failed: %s (%s)",
                exec_result.error_code, exec_result.error_message
            )
            return exec_result

        # =========================================================================
        # READ-ONLY VERIFICATION (NO RETRIES, NO RECURSIVE CLICKS)
        # =========================================================================
        if wait_load:
            time.sleep(0.5)
        else:
            time.sleep(0.1)

        v_passed = True
        v_reason = "Executed successfully"
        if verification_fn:
            try:
                v_passed, v_reason = verification_fn()
            except Exception as v_ex:
                v_passed = False
                v_reason = f"Verification exception: {v_ex}"

        log.info("[VERIFICATION]\nresult=%s\nreason=%s", "PASS" if v_passed else "FAIL", v_reason)

        exec_result.verification_passed = v_passed
        if not v_passed:
            exec_result.error_code = ErrorCode.ACTION_VERIFICATION_FAILED
            exec_result.error_message = f"Action verification failed: {v_reason}"

        return exec_result

    # -------------------------------------------------------------------------
    # Level 1 — Browser DOM Implementation
    # -------------------------------------------------------------------------
    @classmethod
    def _execute_level1_dom(
        cls,
        action_exec: ActionExecution,
        target: UIComponent,
    ) -> Optional[ActionResult]:
        """Direct Browser DOM execution without moving physical mouse."""
        if action_exec.execution_count >= 1:
            log.warning("[ACTION EXECUTION] Rejected: action already executed.")
            return ActionResult(
                success=False,
                action_id=action_exec.action_id,
                execution_count=action_exec.execution_count,
                target_id=target.id,
                source=target.source,
                error_code=ErrorCode.ACTION_ALREADY_EXECUTED,
                error_message="Action has already been executed.",
            )

        try:
            dom_ref = target.dom_reference
            if callable(dom_ref):
                dom_ref()
            elif hasattr(dom_ref, "click") and callable(getattr(dom_ref, "click")):
                dom_ref.click()
            elif isinstance(dom_ref, dict) and "click" in dom_ref:
                dom_ref["click"]()
            else:
                # DOM reference not directly callable
                return None

            action_exec.mark_executed(ExecutionMethod.DOM_CLICK)
            log.info("[ACTION EXECUTION]\nmethod=DOM_CLICK\ntarget=%s", target.id)

            return ActionResult(
                success=True,
                action_id=action_exec.action_id,
                execution_count=action_exec.execution_count,
                execution_method=ExecutionMethod.DOM_CLICK,
                target_id=target.id,
                source=ComponentSource.DOM,
                telemetry={"method": "DOM_CLICK", "dom_ref": str(dom_ref)},
            )
        except Exception as ex:
            log.warning("[ACTION EXECUTION] Level 1 DOM click failed: %s", ex)
            return None

    # -------------------------------------------------------------------------
    # Level 2 — Windows UI Automation Implementation
    # -------------------------------------------------------------------------
    @classmethod
    def _execute_level2_uia(
        cls,
        action_exec: ActionExecution,
        target: UIComponent,
    ) -> Optional[ActionResult]:
        """Windows UI Automation native invoke/click."""
        if action_exec.execution_count >= 1:
            return ActionResult(
                success=False,
                action_id=action_exec.action_id,
                execution_count=action_exec.execution_count,
                target_id=target.id,
                source=target.source,
                error_code=ErrorCode.ACTION_ALREADY_EXECUTED,
                error_message="Action has already been executed.",
            )

        try:
            h_ctrl = target.native_handle
            if sys.platform == "win32" and h_ctrl:
                import ctypes
                user32 = ctypes.windll.user32
                if user32 and user32.IsWindow(h_ctrl):
                    # BM_CLICK = 0x00F5
                    user32.SendMessageW(h_ctrl, 0x00F5, 0, 0)
                    action_exec.mark_executed(ExecutionMethod.UIA_INVOKE)
                    log.info("[ACTION EXECUTION]\nmethod=UIA_INVOKE\nhwnd=%d", h_ctrl)
                    return ActionResult(
                        success=True,
                        action_id=action_exec.action_id,
                        execution_count=action_exec.execution_count,
                        execution_method=ExecutionMethod.UIA_INVOKE,
                        target_id=target.id,
                        source=ComponentSource.UIA,
                        telemetry={"method": "UIA_INVOKE", "native_handle": h_ctrl},
                    )
            return None
        except Exception as ex:
            log.warning("[ACTION EXECUTION] Level 2 UIA invoke failed: %s", ex)
            return None

    # -------------------------------------------------------------------------
    # Level 3 — Screen Coordinate Fallback Implementation
    # -------------------------------------------------------------------------
    @classmethod
    def _execute_level3_screen_coord(
        cls,
        action_exec: ActionExecution,
        target: UIComponent,
        window: Optional[WindowInfo] = None,
    ) -> ActionResult:
        """Physical mouse click fallback with verified trajectory and single-click execution."""
        if action_exec.execution_count >= 1:
            return ActionResult(
                success=False,
                action_id=action_exec.action_id,
                execution_count=action_exec.execution_count,
                target_id=target.id,
                source=target.source,
                error_code=ErrorCode.ACTION_ALREADY_EXECUTED,
                error_message="Action has already been executed.",
            )

        # 1. Resolve Target Geometry
        target_hwnd = window.hwnd if window else 0
        if not target_hwnd:
            fg = WindowManager.get_foreground_window()
            target_hwnd = fg.hwnd if fg else 0

        geom = WindowGeometryProvider.get_window_geometry(hwnd=target_hwnd, app_name="chrome")
        if not geom.is_valid:
            # Fallback geometry if provider failed
            geom = WindowGeometry(
                hwnd=target_hwnd,
                title=window.title if window else "Active Window",
                is_valid=True,
                window_rect=window.bounds if window else (0, 0, 1920, 1080),
                window_x=window.bounds[0] if window else 0,
                window_y=window.bounds[1] if window else 0,
                window_width=window.width if window else 1920,
                window_height=window.height if window else 1080,
                client_rect=window.bounds if window else (0, 0, 1920, 1080),
                client_width=window.width if window else 1920,
                client_height=window.height if window else 1080,
                client_screen_x=window.bounds[0] if window else 0,
                client_screen_y=window.bounds[1] if window else 0,
                browser_chrome_height=80,
                viewport_screen_x=window.bounds[0] if window else 0,
                viewport_screen_y=(window.bounds[1] + 80) if window else 80,
                viewport_width=window.width if window else 1920,
                viewport_height=max(100, (window.height - 80)) if window else 1000,
                dpi=96,
                dpi_scale=1.0,
            )

        from ..ui_perception.models import BoundingBox

        # 2. Derive Click Point (Center of card's thumbnail region)
        comp_bbox = BoundingBox(
            x=target.left,
            y=target.top,
            width=target.width,
            height=target.height,
            space=CoordinateSpace.VIEWPORT_SPACE,
        )
        thumb_h = target.height * 0.65 if target.height > 0 else 180.0
        comp_click_x = target.width * 0.50
        comp_click_y = thumb_h * 0.50
        comp_coord = Coordinate(x=comp_click_x, y=comp_click_y, space=CoordinateSpace.COMPONENT_SPACE)

        # 3. Explicit Coordinate Transformation
        screen_pt, trace = CoordinateResolver.transform_component_to_screen(
            comp_coord=comp_coord,
            component_bbox_in_viewport=comp_bbox,
            geometry=geom,
        )

        if screen_pt is None or not trace.get("success"):
            return ActionResult(
                success=False,
                action_id=action_exec.action_id,
                execution_count=action_exec.execution_count,
                target_id=target.id,
                source=ComponentSource.CV,
                error_code=ErrorCode.ACTION_FAILED,
                error_message="Failed to transform component coordinates to physical screen space.",
            )

        # 4. OS Cursor Telemetry
        cursor_before = MouseController.get_cursor_position(force_fresh=True)

        # 5. Move mouse to target
        move_res = MouseController.move(screen_pt.x, screen_pt.y, tolerance=3)
        if not move_res.get("success", False):
            actual_after = MouseController.get_cursor_position(force_fresh=True)
            log.warning(
                "[MOUSE]\nbefore=(%d,%d)\ntarget=(%d,%d)\nafter=(%d,%d)\nstatus=FAILED",
                cursor_before.x, cursor_before.y, screen_pt.x, screen_pt.y, actual_after.x, actual_after.y
            )
            return ActionResult(
                success=False,
                action_id=action_exec.action_id,
                execution_count=action_exec.execution_count,
                target_id=target.id,
                source=ComponentSource.CV,
                error_code=ErrorCode.MOUSE_MOVE_FAILED,
                error_message=f"Mouse movement to ({screen_pt.x}, {screen_pt.y}) exceeded tolerance.",
            )

        # 6. Execute Single Mouse Click (click_count=1)
        click_res = MouseController.click(screen_pt.x, screen_pt.y, click_count=1, move_first=False)
        cursor_after = MouseController.get_cursor_position(force_fresh=True)

        log.info(
            "[MOUSE]\nbefore=(%d,%d)\ntarget=(%d,%d)\nafter=(%d,%d)",
            cursor_before.x, cursor_before.y, screen_pt.x, screen_pt.y, cursor_after.x, cursor_after.y
        )

        action_exec.mark_executed(ExecutionMethod.MOUSE_CLICK)
        log.info("[ACTION EXECUTION]\nmethod=MOUSE_CLICK\nscreen=(%d,%d)", screen_pt.x, screen_pt.y)

        return ActionResult(
            success=True,
            action_id=action_exec.action_id,
            execution_count=action_exec.execution_count,
            execution_method=ExecutionMethod.MOUSE_CLICK,
            target_id=target.id,
            source=ComponentSource.CV,
            telemetry={
                "cursor_before": cursor_before.to_tuple(),
                "target_point": (screen_pt.x, screen_pt.y),
                "cursor_after": cursor_after.to_tuple(),
                "click_result": click_res,
                "transform_trace": trace,
            },
        )

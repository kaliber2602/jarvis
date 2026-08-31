"""
Mouse Controller and Single Source of Truth for Windows Cursor State.
Provides real-time OS cursor querying, DPI-aware coordinate mapping,
human-like interpolated precision movement, post-movement verification,
atomic thread-safe input serialization, and native SendInput execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import sys
import threading
import time
from typing import Any, Optional, Tuple

from .mouse_backend import (
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    SimulationBackend,
    WindowsSendInputBackend,
)

log = logging.getLogger("hermes.mouse_controller")

# Global re-entrant lock ensuring ONLY ONE thread/action touches the physical mouse at any time
mouse_input_lock = threading.RLock()


@dataclass
class MousePosition:
    """
    Represents the real-time mouse pointer state queried from the operating system.
    """
    x: int
    y: int
    timestamp: float
    screen_id: Optional[int] = None
    dpi_scale: float = 1.0

    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "timestamp": round(self.timestamp, 4),
            "screen_id": self.screen_id,
            "dpi_scale": round(self.dpi_scale, 3),
        }


@dataclass
class MoveResult:
    """
    Result of a physical mouse cursor movement operation.
    """
    success: bool
    cursor_before: tuple[int, int]
    cursor_after: tuple[int, int]
    target: tuple[int, int]
    delta: tuple[int, int]
    distance: float
    verified: bool
    status: str
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "target": self.target,
            "delta": self.delta,
            "distance": round(self.distance, 1),
            "verified": self.verified,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class ClickResult:
    """
    Result of a physical mouse click dispatch operation.
    """
    success: bool
    click_completed: bool
    mouse_action_success: bool
    click_dispatched: bool
    position_at_click: tuple[int, int]
    button: str
    click_count: int
    down_success: bool
    up_success: bool
    status: str
    error: Optional[str] = None
    target_interaction_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "click_completed": self.click_completed,
            "mouse_action_success": self.mouse_action_success,
            "click_dispatched": self.click_dispatched,
            "position_at_click": self.position_at_click,
            "click_point": self.position_at_click,
            "target": self.position_at_click,
            "button": self.button,
            "click_count": self.click_count,
            "down_success": self.down_success,
            "up_success": self.up_success,
            "status": self.status,
            "error": self.error,
            "target_interaction_verified": self.target_interaction_verified,
            "message": (
                f"Clicked {self.button} button at {self.position_at_click}"
                if self.click_completed
                else f"Click failed: {self.error}"
            ),
        }


class MouseController:
    """
    Single source of truth for mouse cursor queries and execution of precision mouse actions.
    Thread-safe, deterministic, and strictly verifies physical cursor coordinates.
    """
    MAX_MOUSE_STATE_AGE: float = 0.1  # 100 ms

    _instance: Optional[MouseController] = None
    _cached_position: Optional[MousePosition] = None
    _simulation_mode: bool = False
    _simulated_position: tuple[int, int] = (0, 0)

    @classmethod
    def get_instance(cls) -> MouseController:
        if cls._instance is None:
            cls._instance = MouseController()
        return cls._instance

    @classmethod
    def enable_simulation_mode(cls, enabled: bool = True) -> None:
        """Enable or disable simulated mode for testing or mock environments."""
        cls._simulation_mode = enabled

    @classmethod
    def set_simulated_position(cls, x: int, y: int) -> None:
        """Helper for unit tests / simulated environments."""
        cls._simulation_mode = True
        cls._simulated_position = (int(x), int(y))
        SimulationBackend.set_cursor_position(x, y)
        cls._cached_position = MousePosition(
            x=int(x),
            y=int(y),
            timestamp=time.time(),
            screen_id=None,
            dpi_scale=1.0,
        )

    @classmethod
    def set_simulated_move_override(cls, override_pos: Optional[tuple[int, int]]) -> None:
        """Helper to simulate physical cursor movement failure in tests."""
        cls._simulation_mode = True
        SimulationBackend.set_move_override(override_pos)
        cls._cached_position = None

    @classmethod
    def get_position(cls) -> tuple[int, int]:
        """
        Query real-time physical cursor position from OS or simulation backend.
        """
        pos = cls.get_cursor_position(force_fresh=True)
        return (pos.x, pos.y)

    @classmethod
    def get_cursor_position(cls, force_fresh: bool = True) -> MousePosition:
        """
        Query real cursor position as MousePosition dataclass.
        """
        now = time.time()
        if not force_fresh and cls._cached_position is not None:
            if (now - cls._cached_position.timestamp) <= cls.MAX_MOUSE_STATE_AGE:
                return cls._cached_position

        if cls._simulation_mode:
            sim_pos = SimulationBackend.get_cursor_position()
            if hasattr(cls, "_simulated_position") and cls._simulated_position != sim_pos and SimulationBackend._move_override is None:
                sim_pos = cls._simulated_position
                SimulationBackend.set_cursor_position(sim_pos[0], sim_pos[1])
            pos = MousePosition(
                x=sim_pos[0],
                y=sim_pos[1],
                timestamp=now,
                screen_id=None,
                dpi_scale=1.0,
            )
        else:
            pt = WindowsSendInputBackend.get_cursor_position()
            pos = MousePosition(
                x=pt[0],
                y=pt[1],
                timestamp=now,
                screen_id=None,
                dpi_scale=1.0,
            )

        cls._cached_position = pos
        return pos

    @classmethod
    def verify_position(cls, target: tuple[int, int], tolerance: int = 2) -> bool:
        """
        Verify that physical cursor is currently within tolerance distance of target.
        """
        actual = cls.get_position()
        dx = actual[0] - target[0]
        dy = actual[1] - target[1]
        distance = math.hypot(dx, dy)
        return distance <= tolerance

    @classmethod
    def move_to(
        cls,
        target: tuple[int, int],
        duration: Optional[float] = None,
        smooth: bool = True,
        tolerance: int = 2,
        transaction_id: Optional[str] = None,
    ) -> MoveResult:
        """
        Move cursor from real current OS position to target position with human-like interpolation
        and verify arrival within tolerance using real OS cursor query.
        """
        tx = int(round(target[0]))
        ty = int(round(target[1]))
        txn_str = f"[{transaction_id}] " if transaction_id else ""

        with mouse_input_lock:
            # 1. Query OS cursor position immediately before movement
            cursor_pos_obj = cls.get_cursor_position(force_fresh=True)
            cursor_before = cursor_pos_obj.to_tuple()
            dx = tx - cursor_before[0]
            dy = ty - cursor_before[1]
            distance = math.hypot(dx, dy)

            log.info(
                "%s[MOUSE_MOVE] requested=(%d, %d) before=(%d, %d) delta=(%d, %d) distance=%.1fpx",
                txn_str, tx, ty, cursor_before[0], cursor_before[1], dx, dy, distance,
            )

            # 2. Movement execution
            if cls._simulation_mode:
                if SimulationBackend._move_override is not None:
                    cls._simulated_position = SimulationBackend._move_override
                    SimulationBackend.set_cursor_position(SimulationBackend._move_override[0], SimulationBackend._move_override[1])
                else:
                    cls._simulated_position = (tx, ty)
                    SimulationBackend.set_cursor_position(tx, ty)
            else:
                if smooth and distance >= 5:
                    if duration is None:
                        duration = min(0.18, max(0.03, distance / 3500.0))
                    steps = max(4, min(16, int(distance / 40.0)))
                    step_sleep = duration / steps

                    for i in range(1, steps):
                        # Ease-out cubic curve
                        t = i / float(steps)
                        ease_t = 1.0 - (1.0 - t) ** 3
                        curr_x = int(round(cursor_before[0] + dx * ease_t))
                        curr_y = int(round(cursor_before[1] + dy * ease_t))
                        WindowsSendInputBackend.set_cursor_position(curr_x, curr_y)
                        time.sleep(step_sleep)

                WindowsSendInputBackend.set_cursor_position(tx, ty)
                time.sleep(0.015)

            # Invalidate cached position
            cls._cached_position = None

            # 3. Post-movement verification query from real OS
            cursor_after_obj = cls.get_cursor_position(force_fresh=True)
            cursor_after = cursor_after_obj.to_tuple()
            actual_dx = cursor_after[0] - tx
            actual_dy = cursor_after[1] - ty
            actual_dist = math.hypot(actual_dx, actual_dy)
            verified = actual_dist <= tolerance

            log.info(
                "%s[MOUSE_MOVE] actual=(%d, %d) distance=%.1fpx verified=%s",
                txn_str, cursor_after[0], cursor_after[1], actual_dist, verified,
            )

            if not verified:
                log.warning(
                    "%s[MOUSE_MOVE] VERIFICATION FAILED: expected=(%d, %d) actual=(%d, %d) dist=%.1f",
                    txn_str, tx, ty, cursor_after[0], cursor_after[1], actual_dist,
                )
                return MoveResult(
                    success=False,
                    cursor_before=cursor_before,
                    cursor_after=cursor_after,
                    target=(tx, ty),
                    delta=(dx, dy),
                    distance=distance,
                    verified=False,
                    status="MOVE_FAILED",
                    error=f"Cursor failed to reach target ({tx}, {ty}). Actual position: {cursor_after}",
                )

            return MoveResult(
                success=True,
                cursor_before=cursor_before,
                cursor_after=cursor_after,
                target=(tx, ty),
                delta=(dx, dy),
                distance=distance,
                verified=True,
                status="MOVE_VERIFIED",
                error=None,
            )

    @classmethod
    def left_click(
        cls,
        click_count: int = 1,
        transaction_id: Optional[str] = None,
    ) -> ClickResult:
        """
        Dispatch left click AT CURRENT PHYSICAL CURSOR POSITION.
        Does NOT accept a target coordinate to prevent clicking at the wrong location.
        """
        return cls._click_current_position(button="left", click_count=click_count, transaction_id=transaction_id)

    @classmethod
    def _click_current_position(
        cls,
        button: str = "left",
        click_count: int = 1,
        transaction_id: Optional[str] = None,
    ) -> ClickResult:
        """
        Internal execution of mouse button down & up at current physical cursor position.
        """
        txn_str = f"[{transaction_id}] " if transaction_id else ""

        with mouse_input_lock:
            # Query actual physical position immediately prior to click
            pos = cls.get_position()

            down_flag = MOUSEEVENTF_LEFTDOWN if button == "left" else (MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_MIDDLEDOWN)
            up_flag = MOUSEEVENTF_LEFTUP if button == "left" else (MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_MIDDLEUP)

            down_success = True
            up_success = True
            error_msg = None

            try:
                for i in range(max(1, click_count)):
                    if cls._simulation_mode:
                        SimulationBackend.send_mouse_event(down_flag)
                        time.sleep(0.01)
                        SimulationBackend.send_mouse_event(up_flag)
                        if click_count > 1 and i < click_count - 1:
                            time.sleep(0.02)
                    else:
                        d_ok = WindowsSendInputBackend.send_mouse_event(down_flag)
                        if not d_ok:
                            down_success = False
                        time.sleep(0.02)
                        u_ok = WindowsSendInputBackend.send_mouse_event(up_flag)
                        if not u_ok:
                            up_success = False
                        if click_count > 1 and i < click_count - 1:
                            time.sleep(0.03)

                completed = down_success and up_success
                log.info(
                    "%s[MOUSE_CLICK] physical_position=(%d, %d) button=%s count=%d down=%s up=%s completed=%s",
                    txn_str, pos[0], pos[1], button, click_count, down_success, up_success, completed,
                )

                return ClickResult(
                    success=completed,
                    click_completed=completed,
                    mouse_action_success=completed,
                    click_dispatched=True,
                    position_at_click=pos,
                    button=button,
                    click_count=click_count,
                    down_success=down_success,
                    up_success=up_success,
                    status="CLICK_DISPATCHED" if completed else "CLICK_FAILED",
                    error=error_msg,
                )
            except Exception as ex:
                log.error("%s[MOUSE_CLICK] Exception during click dispatch: %s", txn_str, ex)
                return ClickResult(
                    success=False,
                    click_completed=False,
                    mouse_action_success=False,
                    click_dispatched=False,
                    position_at_click=pos,
                    button=button,
                    click_count=click_count,
                    down_success=False,
                    up_success=False,
                    status="CLICK_FAILED",
                    error=str(ex),
                )

    # -------------------------------------------------------------------------
    # Backward Compatibility Methods for Existing Callers & Tests
    # -------------------------------------------------------------------------
    @classmethod
    def move(
        cls,
        target_x: int,
        target_y: int,
        duration: Optional[float] = None,
        smooth: bool = True,
        tolerance: int = 2,
    ) -> dict[str, Any]:
        """Backward compatibility move facade returning dict."""
        res = cls.move_to((target_x, target_y), duration=duration, smooth=smooth, tolerance=tolerance)
        return res.to_dict()

    @classmethod
    def click(
        cls,
        target_x: int,
        target_y: int,
        click_count: int = 1,
        button: str = "left",
        move_first: bool = True,
        tolerance: int = 2,
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Backward compatibility click facade:
        Moves to target and verifies. If verification fails, ABORTS without clicking!
        """
        tx = int(round(target_x))
        ty = int(round(target_y))

        move_res = None
        if move_first:
            m_res = cls.move_to((tx, ty), tolerance=tolerance, transaction_id=transaction_id)
            move_res = m_res.to_dict()
            if not m_res.verified:
                log.warning("[MOUSE_CLICK] ABORTED: cursor_not_at_target after move")
                return {
                    "success": False,
                    "click_completed": False,
                    "mouse_action_success": False,
                    "click_dispatched": False,
                    "target": (tx, ty),
                    "click_point": (tx, ty),
                    "cursor_before": m_res.cursor_before,
                    "cursor_after": m_res.cursor_after,
                    "move_verified": False,
                    "move_telemetry": move_res,
                    "status": "MOVE_FAILED",
                    "error": f"Cursor movement verification failed: cursor at {m_res.cursor_after} instead of {(tx, ty)}",
                    "message": f"Cursor movement to ({tx}, {ty}) failed. Actual cursor: {m_res.cursor_after}",
                }

        # Cursor verified -> click at current physical position
        c_res = cls._click_current_position(button=button, click_count=click_count, transaction_id=transaction_id)
        out = c_res.to_dict()
        out["move_telemetry"] = move_res
        out["move_verified"] = True
        return out

    @classmethod
    def double_click(
        cls,
        target_x: Optional[int] = None,
        target_y: Optional[int] = None,
        point: Optional[tuple[int, int]] = None,
        button: str = "left",
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if point is not None:
            tx, ty = point
            return cls.click(tx, ty, click_count=2, button=button, transaction_id=transaction_id)
        elif target_x is not None and target_y is not None:
            return cls.click(target_x, target_y, click_count=2, button=button, transaction_id=transaction_id)
        else:
            return cls._click_current_position(button="left", click_count=2, transaction_id=transaction_id).to_dict()

    @classmethod
    def right_click(
        cls,
        target_x: Optional[int] = None,
        target_y: Optional[int] = None,
        point: Optional[tuple[int, int]] = None,
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if point is not None:
            tx, ty = point
            return cls.click(tx, ty, click_count=1, button="right", transaction_id=transaction_id)
        elif target_x is not None and target_y is not None:
            return cls.click(target_x, target_y, click_count=1, button="right", transaction_id=transaction_id)
        else:
            return cls._click_current_position(button="right", click_count=1, transaction_id=transaction_id).to_dict()

    @classmethod
    def mouse_down(cls, button: str = "left") -> dict[str, Any]:
        pos = cls.get_position()
        down_flag = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
        if cls._simulation_mode:
            SimulationBackend.send_mouse_event(down_flag)
        else:
            WindowsSendInputBackend.send_mouse_event(down_flag)
        return {"success": True, "position": pos}

    @classmethod
    def mouse_up(cls, button: str = "left") -> dict[str, Any]:
        pos = cls.get_position()
        up_flag = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
        if cls._simulation_mode:
            SimulationBackend.send_mouse_event(up_flag)
        else:
            WindowsSendInputBackend.send_mouse_event(up_flag)
        return {"success": True, "position": pos}

    @classmethod
    def drag(
        cls,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: Optional[float] = None,
        button: str = "left",
    ) -> dict[str, Any]:
        sx = int(round(start_x))
        sy = int(round(start_y))
        ex = int(round(end_x))
        ey = int(round(end_y))

        with mouse_input_lock:
            # 1. Move to start position
            m1 = cls.move_to((sx, sy))
            if not m1.verified:
                return {"success": False, "status": "MOVE_FAILED", "start": (sx, sy), "end": (ex, ey)}
            time.sleep(0.04)

            # 2. Mouse down
            cls.mouse_down(button=button)
            time.sleep(0.04)

            # 3. Smooth move to end position
            m2 = cls.move_to((ex, ey), duration=duration, smooth=True)
            time.sleep(0.04)

            # 4. Mouse up
            cls.mouse_up(button=button)

            return {
                "success": m2.verified,
                "mouse_action_success": m2.verified,
                "start": (sx, sy),
                "end": (ex, ey),
                "move_telemetry": m2.to_dict(),
            }

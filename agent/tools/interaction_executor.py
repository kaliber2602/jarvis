"""
Physical Input Interaction Executor.
Standardized low-level execution layer for desktop mouse input.
Enforces strict 2-stage verification: Target -> Move -> Verify Arrival -> Click.
Never dispatches a click if movement verification fails.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Optional
import uuid

from .mouse_controller import ClickResult, MouseController, MoveResult

log = logging.getLogger("hermes.interaction_executor")


class InteractionExecutor:
    """
    Physical OS interaction engine enforcing deterministic input verification.
    """

    @classmethod
    def set_simulation_mode(cls, enabled: bool = True) -> None:
        """Enable or disable simulated mode for testing or mock environments."""
        MouseController.enable_simulation_mode(enabled)

    @classmethod
    def set_simulated_cursor(cls, x: int, y: int) -> None:
        """Set simulated cursor coordinate for unit test validation."""
        MouseController.set_simulated_position(x, y)

    @classmethod
    def set_simulated_move_override(cls, override_pos: Optional[tuple[int, int]]) -> None:
        """Simulate physical cursor movement failure in tests."""
        MouseController.set_simulated_move_override(override_pos)

    @classmethod
    def get_cursor_position(cls) -> tuple[int, int]:
        """Query real physical cursor position from operating system."""
        return MouseController.get_position()

    @classmethod
    def move(
        cls,
        point: tuple[int, int],
        duration: Optional[float] = None,
        smooth: bool = True,
        tolerance: int = 2,
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Move cursor to physical coordinate and verify arrival within tolerance.
        """
        tx = int(round(point[0]))
        ty = int(round(point[1]))
        txn_id = transaction_id or f"TXN-{uuid.uuid4().hex[:8].upper()}"

        log.info("[MOUSE_TXN] id=%s action=MOVE requested=(%d, %d)", txn_id, tx, ty)
        move_res: MoveResult = MouseController.move_to(
            (tx, ty),
            duration=duration,
            smooth=smooth,
            tolerance=tolerance,
            transaction_id=txn_id,
        )

        return move_res.to_dict()

    @classmethod
    def click(
        cls,
        point: tuple[int, int],
        click_count: int = 1,
        button: str = "left",
        move_first: bool = True,
        tolerance: int = 2,
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute physical click at target coordinate with strict verification.
        Invariant:
          1. Move to target coordinate
          2. Verify actual OS cursor position == target coordinate
          3. If verified -> dispatch physical click at current cursor
          4. If NOT verified -> ABORT IMMEDIATELY! Do NOT click!
        """
        tx = int(round(point[0]))
        ty = int(round(point[1]))
        txn_id = transaction_id or f"TXN-{uuid.uuid4().hex[:8].upper()}"

        log.info("[MOUSE_TXN] id=%s action=CLICK target=(%d, %d) count=%d button=%s", txn_id, tx, ty, click_count, button)

        move_dict = None
        if move_first:
            move_res: MoveResult = MouseController.move_to(
                (tx, ty),
                tolerance=tolerance,
                transaction_id=txn_id,
            )
            move_dict = move_res.to_dict()

            if not move_res.verified:
                log.warning(
                    "[MOUSE_TXN] id=%s [MOUSE_CLICK] ABORTED: cursor_not_at_target. expected=(%d, %d) actual=(%d, %d)",
                    txn_id, tx, ty, move_res.cursor_after[0], move_res.cursor_after[1],
                )
                return {
                    "success": False,
                    "click_completed": False,
                    "mouse_action_success": False,
                    "click_dispatched": False,
                    "target": (tx, ty),
                    "requested_point": (tx, ty),
                    "click_point": (tx, ty),
                    "actual_position_before": move_res.cursor_before,
                    "actual_position_after_move": move_res.cursor_after,
                    "cursor_before": move_res.cursor_before,
                    "cursor_after": move_res.cursor_after,
                    "move_verified": False,
                    "move_telemetry": move_dict,
                    "status": "MOVE_FAILED",
                    "error": f"Cursor movement verification failed: cursor at {move_res.cursor_after} instead of {(tx, ty)}",
                    "message": f"Cursor movement to ({tx}, {ty}) failed. Actual cursor: {move_res.cursor_after}",
                }

        # ---------------------------------------------------------------------
        # Final Verification Check Before Physical Click Dispatch
        # ---------------------------------------------------------------------
        actual_cursor = MouseController.get_position()
        delta_x = abs(actual_cursor[0] - tx)
        delta_y = abs(actual_cursor[1] - ty)
        dist = math.hypot(delta_x, delta_y)

        log.info(
            "[MOUSE_TXN] id=%s [MOUSE FINAL CHECK] requested_target=(%d, %d) actual_cursor=(%d, %d) delta=(%d, %d) distance=%.1fpx",
            txn_id, tx, ty, actual_cursor[0], actual_cursor[1], delta_x, delta_y, dist,
        )

        if dist > tolerance:
            log.warning("[MOUSE_TXN] id=%s [MOUSE_CLICK] ABORTED: Final check failed (dist=%.1f > %d)", txn_id, dist, tolerance)
            return {
                "success": False,
                "click_completed": False,
                "mouse_action_success": False,
                "click_dispatched": False,
                "target": (tx, ty),
                "requested_point": (tx, ty),
                "click_point": (tx, ty),
                "actual_position_at_click": actual_cursor,
                "move_verified": False,
                "status": "MOVE_FAILED",
                "error": f"Final position check failed before click: cursor at {actual_cursor}",
                "message": f"Cursor drifted from target before click. Actual position: {actual_cursor}",
            }

        # ---------------------------------------------------------------------
        # Physical Click Dispatch at Verified Position
        # ---------------------------------------------------------------------
        if button == "right":
            click_res: ClickResult = MouseController.right_click(click_count=click_count, transaction_id=txn_id)
        elif click_count == 2:
            click_res = MouseController.double_click(transaction_id=txn_id)
        else:
            click_res = MouseController.left_click(click_count=click_count, transaction_id=txn_id)

        log.info(
            "[MOUSE_TXN] id=%s [MOUSE CLICK RESULT] position_at_click=(%d, %d) down_result=%s up_result=%s click_completed=%s",
            txn_id, click_res.position_at_click[0], click_res.position_at_click[1],
            click_res.down_success, click_res.up_success, click_res.click_completed,
        )

        result_dict = click_res.to_dict()
        result_dict["target"] = (tx, ty)
        result_dict["requested_point"] = (tx, ty)
        result_dict["actual_position_before"] = move_dict.get("cursor_before") if move_dict else actual_cursor
        result_dict["actual_position_at_click"] = click_res.position_at_click
        result_dict["cursor_before"] = result_dict["actual_position_before"]
        result_dict["cursor_after"] = result_dict["actual_position_at_click"]
        result_dict["move_verified"] = True
        result_dict["move_telemetry"] = move_dict
        return result_dict

    @classmethod
    def double_click(cls, point: tuple[int, int], button: str = "left", transaction_id: Optional[str] = None) -> dict[str, Any]:
        return cls.click(point, click_count=2, button=button, transaction_id=transaction_id)

    @classmethod
    def right_click(cls, point: tuple[int, int], transaction_id: Optional[str] = None) -> dict[str, Any]:
        return cls.click(point, click_count=1, button="right", transaction_id=transaction_id)

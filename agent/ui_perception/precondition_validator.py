"""
Target Precondition Validator.
Replaces post-click target verification with deterministic pre-click validation.
Validates all 12 critical preconditions prior to physical click dispatch.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .coordinates import Coordinate, CoordinateResolver, CoordinateSpace, WindowGeometry
from .models import (
    BoundingBox,
    Point,
    PreconditionValidationResult,
    ResolutionStatus,
    SafeClickRegion,
    UIElement,
    UISnapshot,
    UITree,
    VisibilityState,
)

log = logging.getLogger("hermes_ui.precondition_validator")


class TargetPreconditionValidator:
    """
    Evaluates all 12 strict preconditions before any click action is executed.
    If any precondition fails: DO NOT CLICK -> INVALID_TARGET_BEFORE_CLICK.
    """

    @classmethod
    def validate_preconditions(
        cls,
        target_element: Optional[UIElement],
        tree: Optional[UITree] = None,
        snapshot: Optional[UISnapshot] = None,
        safe_region: Optional[SafeClickRegion] = None,
        local_click_point: Optional[tuple[float, float] | Point] = None,
        screen_click_point: Optional[tuple[int, int]] = None,
        current_window_info: Optional[dict[str, Any]] = None,
        viewport_size: Optional[tuple[float, float]] = None,
        max_snapshot_age_seconds: float = 5.0,
    ) -> PreconditionValidationResult:
        """
        Run the complete 12-point pre-click validation check.
        """
        checked: dict[str, bool] = {}
        failed: list[str] = []
        details: dict[str, Any] = {}

        # 1. Target component exists
        c1 = target_element is not None
        checked["target_exists"] = c1
        if not c1:
            failed.append("target_exists")
            return PreconditionValidationResult(
                valid=False,
                status=ResolutionStatus.TARGET_NOT_FOUND,
                failed_preconditions=failed,
                checked_preconditions=checked,
                reason="Target component is None / does not exist",
            )

        elem: UIElement = target_element

        # 2. Target belongs to current UI snapshot
        c2 = True
        if snapshot and hasattr(snapshot, "detected_components") and snapshot.detected_components:
            snap_ids = [
                getattr(c, "id", c.get("id") if isinstance(c, dict) else str(c))
                for c in snapshot.detected_components
            ]
            c2 = (elem.id in snap_ids) or any(elem.id in str(sid) for sid in snap_ids)
        elif tree and hasattr(tree, "elements"):
            c2 = elem.id in tree.elements
        checked["snapshot_match"] = c2
        if not c2:
            failed.append("snapshot_match")

        # 3. Target component visible
        vis_val = elem.visibility
        c3 = (
            vis_val not in (VisibilityState.OFFSCREEN, VisibilityState.HIDDEN)
            and not getattr(elem, "is_offscreen", False)
            and getattr(elem, "interactive", True)
        )
        checked["is_visible"] = c3
        if not c3:
            failed.append("is_visible")

        # 4. Target bbox is valid
        bbox = elem.bbox
        c4 = (
            bbox is not None
            and bbox.width > 0
            and bbox.height > 0
            and not (bbox.width == 0 and bbox.height == 0)
        )
        checked["bbox_valid"] = c4
        if not c4:
            failed.append("bbox_valid")

        # 5. Target bbox has reasonable dimensions
        if viewport_size and viewport_size[0] > 0 and viewport_size[1] > 0:
            vp_w, vp_h = float(viewport_size[0]), float(viewport_size[1])
        elif tree and tree.screen_width > 0 and tree.screen_height > 0:
            vp_w, vp_h = float(tree.screen_width), float(tree.screen_height)
        else:
            vp_w, vp_h = 1920.0, 1080.0
        c5 = (
            c4
            and bbox.width >= 20.0
            and bbox.height >= 20.0
            and bbox.width <= vp_w * 1.5
            and bbox.height <= vp_h * 1.5
        )
        checked["bbox_reasonable_size"] = c5
        if not c5:
            failed.append("bbox_reasonable_size")

        # 6. Target is not occluded severely
        c6 = not getattr(elem, "is_occluded", False)
        if tree:
            blocking = tree.find_blocking_overlay()
            if blocking and blocking.visibility == VisibilityState.VISIBLE:
                # Modal blocking WebPage interactions
                if elem.scope != "OVERLAY" and elem.scope != "MODAL":
                    c6 = False
        checked["not_occluded"] = c6
        if not c6:
            failed.append("not_occluded")

        # 7. Target is not outside viewport
        c7 = (
            bbox.right > 0
            and bbox.bottom > 0
            and bbox.left < vp_w
            and bbox.top < vp_h
            and vis_val != VisibilityState.OFFSCREEN
        )
        checked["in_viewport"] = c7
        if not c7:
            failed.append("in_viewport")

        # 8. Target is not covered by an interactive overlapping component
        c8 = True
        if tree and hasattr(tree, "elements"):
            for other_id, other in tree.elements.items():
                if other_id == elem.id or other.parent_id == elem.id or elem.parent_id == other_id:
                    continue
                if other.z_order > elem.z_order and other.visibility == VisibilityState.VISIBLE:
                    if other.bbox.contains_bbox(bbox) and other.interactive:
                        c8 = False
                        break
        checked["not_covered"] = c8
        if not c8:
            failed.append("not_covered")

        # 9. Click point is inside safe click region of target
        c9 = True
        pt_obj = None
        if local_click_point is not None:
            if isinstance(local_click_point, Point):
                pt_obj = local_click_point
            elif isinstance(local_click_point, (tuple, list)) and len(local_click_point) >= 2:
                pt_obj = Point(float(local_click_point[0]), float(local_click_point[1]))

        if safe_region and pt_obj:
            c9 = safe_region.contains_local_point(pt_obj)
        elif pt_obj:
            # Fallback: check if local point is inside component dimensions with 5% margin
            margin_x = bbox.width * 0.05
            margin_y = bbox.height * 0.05
            c9 = (margin_x <= pt_obj.x <= (bbox.width - margin_x) and margin_y <= pt_obj.y <= (bbox.height - margin_y))
        checked["point_in_safe_region"] = c9
        if not c9:
            failed.append("point_in_safe_region")

        # 10. Click point can be converted deterministically to screen coordinates
        c10 = True
        if screen_click_point is not None:
            sx, sy = screen_click_point
            c10 = (sx >= -10000 and sy >= -10000 and sx <= 30000 and sy <= 30000)
        checked["screen_coord_valid"] = c10
        if not c10:
            failed.append("screen_coord_valid")

        # 11. Window context currently matches perception snapshot
        c11 = True
        if current_window_info and snapshot:
            curr_hwnd = current_window_info.get("hwnd")
            if curr_hwnd and snapshot.window_hwnd and curr_hwnd != snapshot.window_hwnd:
                c11 = False
            curr_pid = current_window_info.get("pid") or current_window_info.get("process_id")
            if curr_pid and snapshot.process_id and curr_pid != snapshot.process_id:
                c11 = False
        checked["window_context_matches"] = c11
        if not c11:
            failed.append("window_context_matches")

        # 12. No sign that UI has changed between perception and click (snapshot not stale)
        c12 = True
        if snapshot:
            age = time.time() - snapshot.timestamp
            if age > max_snapshot_age_seconds:
                c12 = False
        if tree and hasattr(tree, "stability_score"):
            if tree.stability_score < 0.60:
                c12 = False
        checked["snapshot_not_stale"] = c12
        if not c12:
            failed.append("snapshot_not_stale")

        all_valid = (len(failed) == 0)
        details["checked_count"] = len(checked)
        details["passed_count"] = len(checked) - len(failed)
        details["failed_items"] = failed

        status = ResolutionStatus.SUCCESS if all_valid else (
            ResolutionStatus.SNAPSHOT_STALE if "snapshot_not_stale" in failed or "window_context_matches" in failed
            else (
                ResolutionStatus.TARGET_OFFSCREEN if "in_viewport" in failed or "is_visible" in failed
                else (
                    ResolutionStatus.TARGET_OCCLUDED if "not_occluded" in failed or "not_covered" in failed
                    else (
                        ResolutionStatus.SAFE_REGION_INVALID if "point_in_safe_region" in failed or "bbox_valid" in failed
                        else ResolutionStatus.INVALID_TARGET_BEFORE_CLICK
                    )
                )
            )
        )

        reason = "All 12 pre-click preconditions passed" if all_valid else f"Preconditions failed: {', '.join(failed)}"
        log.info(
            "[PRECLICK VALIDATION] valid=%s failed=%s checked_count=%d",
            all_valid, failed, len(checked)
        )

        return PreconditionValidationResult(
            valid=all_valid,
            status=status,
            failed_preconditions=failed,
            checked_preconditions=checked,
            details=details,
            reason=reason,
        )

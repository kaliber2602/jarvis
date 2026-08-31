"""
Hermes UI Service: Central Coordinator Facade for UI Perception,
Semantic Tree Building, Target Resolution, Safe Interaction, and Action Verification.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from .component_detector import VisualComponentDetector
from .composite_builder import CompositeBuilder
from .layout_engine import LayoutEngine
from .models import (
    ActionType,
    BoundingBox,
    ElementType,
    InteractionPoint,
    ResolutionResult,
    ResolutionStatus,
    TargetQuery,
    UIElement,
    UITree,
    VerificationResult,
)
from .region_detector import RegionDetector
from .screenshot_manager import ScreenshotManager
from .spatial_reasoner import SpatialReasoner
from .target_resolver import TargetResolver
from .tree_builder import TreeBuilder
from .verification_engine import VerificationEngine

log = logging.getLogger("hermes_ui.service")


class HermesUIService:
    """
    Unified UI Perception, Understanding, Targeting, and Verification Subsystem for Hermes Agent.
    """

    _instance: Optional[HermesUIService] = None

    @classmethod
    def get_instance(cls) -> HermesUIService:
        if cls._instance is None:
            cls._instance = HermesUIService()
        return cls._instance

    def __init__(self):
        self.screenshot_mgr = ScreenshotManager()
        self.region_detector = RegionDetector()
        self.component_detector = VisualComponentDetector()
        self.layout_engine = LayoutEngine()
        self.composite_builder = CompositeBuilder()
        self.spatial_reasoner = SpatialReasoner()
        self.target_resolver = TargetResolver()
        self.tree_builder = TreeBuilder()
        self.verification_engine = VerificationEngine(self.screenshot_mgr)

        # Cache of the most recent perceived UI Tree and window geometry
        self.last_tree: Optional[UITree] = None
        self.last_tree_time: float = 0.0
        self.last_geometry: Optional[Any] = None

    def perceive_active_window(
        self,
        raw_elements: Optional[list[dict[str, Any]]] = None,
        force_fresh: bool = False,
        hwnd: Optional[int] = None,
    ) -> UITree:
        """
        Perceive the active foreground window or specified HWND, inspect regions and layout, and construct the Semantic UI Tree.
        """
        # 1. Inspect window geometry & capture screen
        img, w_bbox, win_info = self.screenshot_mgr.capture_active_window(hwnd=hwnd)
        self.last_geometry = win_info.get("geometry")
        stability = 1.0

        if not raw_elements:
            # Measure visual frame stability
            stability = self.screenshot_mgr.compute_stability_score(
                self.screenshot_mgr.last_capture,
                img,
            )
            # Detect visual components automatically from image & window geometry
            raw_elements = self.component_detector.detect_components(win_info, image=img)

        # 2. Build Semantic UI Tree
        tree = self.tree_builder.build_tree(
            screen_width=int(w_bbox.width) or 1920,
            screen_height=int(w_bbox.height) or 1080,
            window_title=win_info.get("title", ""),
            app_name=win_info.get("app", "chrome"),
            is_browser=win_info.get("is_browser", True),
            is_youtube=win_info.get("is_youtube", False),
            stability_score=stability,
            raw_elements_data=raw_elements,
        )

        self.last_tree = tree
        self.last_tree_time = time.time()
        log.info(
            "[HermesUI] Perceived window '%s' (Elements: %d, Composites: %d, Stability: %.2f)",
            tree.window_title, len(tree.elements), len(tree.composites), tree.stability_score
        )
        return tree

    def resolve_target(
        self,
        query: str | TargetQuery,
        tree: Optional[UITree] = None,
        action: Optional[ActionType] = None,
    ) -> ResolutionResult:
        """
        Resolve user natural language target description on the active or provided UI Tree.
        """
        active_tree = tree or self.last_tree or self.perceive_active_window()
        return self.target_resolver.resolve(active_tree, query, action=action)

    def interact_with_target(
        self,
        query: str | TargetQuery,
        action: Optional[ActionType] = None,
        tree: Optional[UITree] = None,
        click_callback: Optional[Callable[[int, int, float, float], Any]] = None,
        max_retries: int = 0,
    ) -> tuple[ResolutionResult, Optional[VerificationResult]]:
        """
        Full pre-click deterministic targeting pipeline:
        1. Perceive & Build Semantic Tree
        2. Resolve Target & Safe Interaction Point (via Spatial Ordering)
        3. Validate 12 Preconditions (Pre-Click Validation)
        4. Execute Click / Interaction Once (CLICK_ONCE)
        5. Passive Post-Click Observation for State Synchronization (ZERO Retries)
        """
        active_tree = tree or self.perceive_active_window()

        # Step 1: Pre-action state snapshot
        pre_state = self.verification_engine.capture_pre_action_state(active_tree)

        # Step 2: Target Resolution
        res = self.resolve_target(query, tree=active_tree, action=action)
        if not res.is_success():
            log.warning("[HermesUI] Target resolution failed: %s (%s)", res.status.value, res.error_message)
            return res, None

        # Step 3: Target Precondition Validation (Pre-Click)
        from .precondition_validator import TargetPreconditionValidator
        pt = res.interaction_point
        val_res = TargetPreconditionValidator.validate_preconditions(
            target_element=res.target_element,
            tree=active_tree,
            local_click_point=(pt.pixel_x, pt.pixel_y) if pt else None,
            screen_click_point=(pt.pixel_x, pt.pixel_y) if pt else None,
        )

        if not val_res.valid:
            log.warning("[HermesUI] Pre-click validation failed: %s (%s)", val_res.status.value, val_res.reason)
            res.status = val_res.status
            res.error_message = val_res.reason
            return res, None

        log.info(
            "[HermesUI] Preconditions passed. Executing interaction '%s' at (%d, %d) [Normalized: (%.3f, %.3f)] for target '%s' (click_count=1)",
            action.value if action else "CLICK", pt.pixel_x, pt.pixel_y, pt.normalized_x, pt.normalized_y, pt.target_element_id
        )

        # Step 4: Execute Exactly-Once Click Callback
        if click_callback:
            try:
                click_callback(pt.pixel_x, pt.pixel_y, pt.normalized_x, pt.normalized_y)
            except Exception as e:
                log.error("[HermesUI] Error during click execution callback: %s", e)

        # Step 5: Short wait for UI transition
        time.sleep(0.35)

        # Step 6: Passive Post-Click Observation (State Synchronization Only — ZERO Retries)
        post_tree = self.perceive_active_window()
        verif = self.verification_engine.verify_action_result(
            pre_state=pre_state,
            post_tree=post_tree,
            target_element=res.target_element,
            action_type=action or ActionType.CLICK,
        )

        # Invariant: Action completed once clicked. No retries or re-localization loops.
        return res, verif


def get_ui_service() -> HermesUIService:
    return HermesUIService.get_instance()

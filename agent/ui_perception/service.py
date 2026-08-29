"""
Hermes UI Service: Central Coordinator Facade for UI Perception,
Semantic Tree Building, Target Resolution, Safe Interaction, and Action Verification.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

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
        self.layout_engine = LayoutEngine()
        self.composite_builder = CompositeBuilder()
        self.spatial_reasoner = SpatialReasoner()
        self.target_resolver = TargetResolver()
        self.tree_builder = TreeBuilder()
        self.verification_engine = VerificationEngine(self.screenshot_mgr)

        # Cache of the most recent perceived UI Tree
        self.last_tree: Optional[UITree] = None
        self.last_tree_time: float = 0.0

    def perceive_active_window(
        self,
        raw_elements: Optional[list[dict[str, Any]]] = None,
        force_fresh: bool = False,
    ) -> UITree:
        """
        Perceive the active foreground window, inspect regions and layout, and construct the Semantic UI Tree.
        """
        # 1. Inspect window geometry & stability
        win_info = self.screenshot_mgr.get_active_window_geometry()
        w_bbox = win_info["bbox"]
        stability = 1.0

        if not raw_elements:
            # Measure visual frame stability
            stability = self.screenshot_mgr.compute_stability_score(
                self.screenshot_mgr.last_capture,
                self.screenshot_mgr.capture_screen()
            )

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
        max_retries: int = 1,
    ) -> tuple[ResolutionResult, Optional[VerificationResult]]:
        """
        Full end-to-end execution pipeline:
        1. Perceive & Build Semantic Tree
        2. Resolve Target & Safe Interaction Point
        3. Check Modal Blocking & Occlusion
        4. Execute Click / Interaction
        5. Verify State Change & Re-localize if needed
        """
        active_tree = tree or self.perceive_active_window()

        # Step 1: Pre-action state snapshot
        pre_state = self.verification_engine.capture_pre_action_state(active_tree)

        # Step 2: Target Resolution
        res = self.resolve_target(query, tree=active_tree, action=action)
        if not res.is_success():
            log.warning("[HermesUI] Target resolution failed: %s (%s)", res.status.value, res.error_message)
            return res, None

        pt = res.interaction_point
        log.info(
            "[HermesUI] Executing interaction '%s' at (%d, %d) [Normalized: (%.3f, %.3f)] for target '%s'",
            action.value, pt.pixel_x, pt.pixel_y, pt.normalized_x, pt.normalized_y, pt.target_element_id
        )

        # Step 3: Execute Click Callback
        if click_callback:
            try:
                click_callback(pt.pixel_x, pt.pixel_y, pt.normalized_x, pt.normalized_y)
            except Exception as e:
                log.error("[HermesUI] Error during click execution callback: %s", e)

        # Step 4: Short wait for UI transition
        time.sleep(0.35)

        # Step 5: Post-Action Verification
        post_tree = self.perceive_active_window()
        verif = self.verification_engine.verify_action_result(
            pre_state=pre_state,
            post_tree=post_tree,
            target_element=res.target_element,
            action_type=action,
        )

        # Step 6: Re-localization if verification failed and retries remain
        if not verif.success and max_retries > 0:
            log.info("[HermesUI] Re-localizing and retrying interaction...")
            return self.interact_with_target(
                query=query,
                action=action,
                tree=post_tree,
                click_callback=click_callback,
                max_retries=max_retries - 1,
            )

        return res, verif


def get_ui_service() -> HermesUIService:
    return HermesUIService.get_instance()

"""
Multi-Factor Target Resolution, Candidate Ranking, Safe Click Point Calculation,
and Visual Ambiguity Guard Engine.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Sequence

from .composite_builder import CompositeBuilder
from .coordinates import Coordinate, CoordinateSpace
from .models import (
    ActionType,
    BoundingBox,
    CandidateMatch,
    CompositeComponent,
    ElementType,
    InteractionPoint,
    Point,
    RegionType,
    ResolutionResult,
    ResolutionStatus,
    SpatialRelation,
    TargetQuery,
    UIElement,
    UITree,
    VisibilityState,
)
from .spatial_reasoner import SpatialReasoner

log = logging.getLogger("hermes_ui.target_resolver")


class TargetResolver:
    """
    Resolves natural user queries to precise UI targets and safe interaction points.
    """

    ORDINAL_MAP: dict[str, int] = {
        "đầu tiên": 0, "dau tien": 0, "first": 0, "1st": 0, "1": 0, "một": 0, "mot": 0,
        "thứ nhất": 0, "thu nhat": 0, "thứ 1": 0, "thu 1": 0, "item 1": 0, "video 1": 0,
        "thứ hai": 1, "thu hai": 1, "second": 1, "2nd": 1, "2": 1, "hai": 1,
        "thứ 2": 1, "thu 2": 1, "item 2": 1, "video 2": 1,
        "thứ ba": 2, "thu ba": 2, "third": 2, "3rd": 2, "3": 2, "ba": 2,
        "thứ 3": 2, "thu 3": 2, "item 3": 2, "video 3": 2,
        "thứ bốn": 3, "thu bon": 3, "thứ tư": 3, "thu tu": 3, "fourth": 3, "4th": 3, "4": 3, "bốn": 3, "bon": 3, "tư": 3, "tu": 3,
        "thứ 4": 3, "thu 4": 3, "item 4": 3, "video 4": 3,
        "thứ năm": 4, "thu nam": 4, "fifth": 4, "5th": 4, "5": 4, "năm": 4, "nam": 4,
        "thứ 5": 4, "thu 5": 4, "item 5": 4, "video 5": 4,
        "thứ sáu": 5, "thu sau": 5, "sixth": 5, "6th": 5, "6": 5, "sáu": 5, "sau": 5,
        "thứ 6": 5, "thu 6": 5, "item 6": 5, "video 6": 5,
        "thứ bảy": 6, "thu bay": 6, "seventh": 6, "7th": 6, "7": 6, "bảy": 6, "bay": 6,
        "thứ 7": 6, "thu 7": 6, "item 7": 6, "video 7": 6,
        "thứ tám": 7, "thu tam": 7, "eighth": 7, "8th": 7, "8": 7, "tám": 7, "tam": 7,
        "thứ 8": 7, "thu 8": 7, "item 8": 7, "video 8": 7,
        "thứ chín": 8, "thu chin": 8, "ninth": 8, "9th": 8, "9": 8, "chín": 8, "chin": 8,
        "thứ 9": 8, "thu 9": 8, "item 9": 8, "video 9": 8,
        "thứ mười": 9, "thu muoi": 9, "tenth": 9, "10th": 9, "10": 9, "mười": 9, "muoi": 9,
        "thứ 10": 9, "thu 10": 9, "item 10": 9, "video 10": 9,
    }

    def __init__(self):
        self.spatial_reasoner = SpatialReasoner()
        self.composite_builder = CompositeBuilder()

    def parse_query(self, query_text: str) -> TargetQuery:
        """
        Parse natural language target description into structured TargetQuery.
        """
        q = (query_text or "").strip()
        q_low = q.lower()

        t_query = TargetQuery(raw_query=q)

        # 1. Determine Semantic Type
        if "short" in q_low or "shorts" in q_low:
            t_query.semantic_type = ElementType.SHORT_CARD
            t_query.section_name = "SHORTS"
        elif "playlist" in q_low:
            t_query.section_name = "PLAYLIST"
            if "mục" in q_low or "item" in q_low or "video" in q_low or "bài" in q_low:
                t_query.semantic_type = ElementType.PLAYLIST_ITEM
            else:
                t_query.semantic_type = ElementType.PLAYLIST
        elif "sidebar" in q_low or "menu bên trái" in q_low or "thanh bên" in q_low:
            t_query.section_name = "SIDEBAR"
            t_query.semantic_type = ElementType.SIDEBAR_ITEM
        elif "navbar" in q_low or "thanh điều hướng" in q_low or "thanh tab" in q_low or "category" in q_low:
            t_query.section_name = "NAVBAR"
            t_query.semantic_type = ElementType.NAV_ITEM
        elif "tìm kiếm" in q_low or "search" in q_low:
            if "nút" in q_low or "button" in q_low:
                t_query.semantic_type = ElementType.SEARCH_BUTTON
            else:
                t_query.semantic_type = ElementType.SEARCH_INPUT
        elif "video" in q_low or "clip" in q_low or "bài hát" in q_low or "bài" in q_low or "phim" in q_low:
            t_query.semantic_type = ElementType.VIDEO_CARD
        elif "nút" in q_low or "button" in q_low or "icon" in q_low:
            t_query.semantic_type = ElementType.BUTTON
        elif "tab" in q_low:
            t_query.semantic_type = ElementType.TAB

        # 2. Check for Sub-Component target (e.g. More Button / 3-dots, Title, Thumbnail)
        if any(mb in q_low for mb in ("ba chấm", "3 chấm", "ba cham", "3 cham", "more button", "menu", "tùy chọn", "options")):
            t_query.child_type = ElementType.MORE_BUTTON
            t_query.action_type = ActionType.OPEN_MENU
        elif "tiêu đề" in q_low or "title" in q_low:
            t_query.child_type = ElementType.TITLE
        elif "thumbnail" in q_low or "hình thu nhỏ" in q_low or "ảnh bìa" in q_low:
            t_query.child_type = ElementType.THUMBNAIL

        # 3. Extract Ordinal Index
        for phrase, idx_val in self.ORDINAL_MAP.items():
            pattern = r"\b" + re.escape(phrase) + r"\b"
            if re.search(pattern, q_low):
                t_query.ordinal_index = idx_val
                break

        # Fallback numeric extraction: "thứ 2", "#3", "số 4"
        if t_query.ordinal_index is None:
            num_match = re.search(r"(?:thứ|thu|số|so|#|number)\s*(\d+)", q_low)
            if num_match:
                t_query.ordinal_index = int(num_match.group(1)) - 1

        # 4. Extract Row / Column Specifications
        if any(r in q_low for r in ("hàng đầu", "hang dau", "hàng 1", "hàng nhất", "top row", "first row")):
            t_query.row = 0
        elif any(r in q_low for r in ("hàng 2", "hàng hai", "hàng thứ 2", "second row", "hàng thứ hai", "hàng dưới")):
            t_query.row = 1
        elif any(r in q_low for r in ("hàng 3", "hàng ba", "hàng thứ 3", "third row")):
            t_query.row = 2

        if any(c in q_low for c in ("cột 1", "cột đầu", "cột nhất", "first column", "bên trái", "ngoài cùng bên trái")):
            t_query.column = 0
        elif any(c in q_low for c in ("cột 2", "cột hai", "second column")):
            t_query.column = 1
        elif any(c in q_low for c in ("cột 3", "cột ba", "third column", "bên phải", "ngoài cùng bên phải")):
            t_query.column = 2

        # 5. Extract Text Title / Query Substring
        title_match = re.search(r'(?:tiêu đề|tên là|tựa đề|title|named|called|với từ khóa|về)\s+["\']?([^"\']+)["\']?', q, re.IGNORECASE)
        if title_match:
            t_query.text_pattern = title_match.group(1).strip()
        elif '"' in q or "'" in q:
            quote_match = re.search(r'["\']([^"\']+)["\']', q)
            if quote_match:
                t_query.text_pattern = quote_match.group(1).strip()

        # 6. Extract Relative Spatial Relations
        if "bên phải" in q_low or "right of" in q_low or "phía bên phải" in q_low:
            t_query.spatial_relation = SpatialRelation.RIGHT_OF
            anchor_m = re.search(r"(?:bên phải|right of|phía bên phải)\s+(.+)", q_low)
            if anchor_m:
                t_query.anchor_query = anchor_m.group(1).strip()
        elif "bên trái" in q_low or "left of" in q_low:
            t_query.spatial_relation = SpatialRelation.LEFT_OF
            anchor_m = re.search(r"(?:bên trái|left of)\s+(.+)", q_low)
            if anchor_m:
                t_query.anchor_query = anchor_m.group(1).strip()
        elif "ở dưới" in q_low or "ngay dưới" in q_low or "dưới" in q_low or "below" in q_low:
            t_query.spatial_relation = SpatialRelation.BELOW
            anchor_m = re.search(r"(?:ở dưới|ngay dưới|dưới|below)\s+(.+)", q_low)
            if anchor_m:
                t_query.anchor_query = anchor_m.group(1).strip()
        elif "ở trên" in q_low or "ngay trên" in q_low or "above" in q_low:
            t_query.spatial_relation = SpatialRelation.ABOVE
            anchor_m = re.search(r"(?:ở trên|ngay trên|above)\s+(.+)", q_low)
            if anchor_m:
                t_query.anchor_query = anchor_m.group(1).strip()

        return t_query

    def resolve(
        self,
        tree: UITree,
        query: str | TargetQuery,
        action: Optional[ActionType] = None,
    ) -> ResolutionResult:
        """
        Resolve user query to best candidate target and safe interaction point.
        """
        t_query = self.parse_query(query) if isinstance(query, str) else query
        if action is not None:
            t_query.action_type = action

        # 0. Check UI Stability
        if tree.stability_score < 0.70:
            log.warning("[TARGET_RESOLVER] UI stability score too low (%.2f)", tree.stability_score)
            return ResolutionResult(
                status=ResolutionStatus.UI_UNSTABLE,
                query=t_query,
                confidence=tree.stability_score,
                error_message="UI is currently unstable (loading/animating).",
            )

        # 0.1 Check for Blocking Modal / Dialog Overlay
        blocking_modal = tree.find_blocking_overlay()
        if blocking_modal:
            # If query is not specifically addressing the modal, interactions are blocked!
            if not t_query.section_name or "modal" not in t_query.section_name.lower():
                log.info("[TARGET_RESOLVER] Active blocking modal '%s' detected.", blocking_modal.id)
                return ResolutionResult(
                    status=ResolutionStatus.TARGET_OCCLUDED,
                    query=t_query,
                    error_message=f"Target occluded by active blocking modal ({blocking_modal.id}).",
                    suggested_action=f"DISMISS_MODAL:{blocking_modal.id}",
                )

        # 1. Candidate Extraction & Container Anchor Identification
        candidates = self._gather_candidates(tree, t_query)
        if not candidates:
            log.warning("[TARGET_RESOLVER] No candidates found for query '%s'", t_query.raw_query)
            return ResolutionResult(
                status=ResolutionStatus.TARGET_NOT_FOUND,
                query=t_query,
                error_message=f"No UI elements found matching '{t_query.raw_query}'.",
            )

        # 2. Score Candidates
        scored_matches: list[CandidateMatch] = []
        for elem in candidates:
            comp = tree.get_composite(elem.id) or tree.get_composite(elem.parent_id or "")
            match = self._score_candidate(elem, comp, t_query, tree)
            scored_matches.append(match)

        # Sort candidates descending by total score
        scored_matches.sort(key=lambda m: m.total_score, reverse=True)

        if not scored_matches:
            return ResolutionResult(
                status=ResolutionStatus.TARGET_NOT_FOUND,
                query=t_query,
                error_message="All candidates scored below threshold.",
            )

        best_match = scored_matches[0]
        top_score = best_match.total_score

        # 3. Check for Ambiguity Threshold
        # If top 2 candidates have nearly identical scores and confidence gap is too small, flag ambiguous!
        if len(scored_matches) > 1:
            second_score = scored_matches[1].total_score
            score_gap = top_score - second_score
            if top_score > 0.70 and score_gap < 0.05 and t_query.ordinal_index is None and not t_query.text_pattern:
                log.info(
                    "[TARGET_RESOLVER] Ambiguity detected between '%s' (%.2f) and '%s' (%.2f) (gap: %.3f)",
                    best_match.element.id, top_score, scored_matches[1].element.id, second_score, score_gap
                )
                return ResolutionResult(
                    status=ResolutionStatus.TARGET_AMBIGUOUS,
                    query=t_query,
                    confidence=top_score,
                    candidates_count=len(scored_matches),
                    top_candidates=scored_matches[:3],
                    error_message=f"Multiple ambiguous targets found ({len(scored_matches)} candidates).",
                )

        # 4. Check Visibility
        if best_match.element.visibility == VisibilityState.OFFSCREEN:
            cont_id = best_match.element.container_id or "PAGE_SCROLL"
            return ResolutionResult(
                status=ResolutionStatus.TARGET_OFFSCREEN,
                query=t_query,
                target_element=best_match.element,
                composite=best_match.composite,
                confidence=top_score,
                suggested_action=f"SCROLL_CONTAINER:{cont_id}",
                error_message="Target is offscreen. Scroll required.",
            )

        # 5. Resolve Semantic Target vs Interaction Target & Safe Click Point
        interaction_point = self.calculate_safe_interaction_point(
            best_match.element,
            best_match.composite,
            t_query.child_type,
            t_query.action_type,
            tree,
        )

        log.info(
            "[TARGET_RESOLVER] Resolved target '%s' (type=%s, score=%.2f) -> Interaction Point: (%d, %d)",
            best_match.element.id, best_match.element.type.value, top_score,
            interaction_point.pixel_x, interaction_point.pixel_y
        )

        return ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            query=t_query,
            target_element=best_match.element,
            composite=best_match.composite,
            interaction_point=interaction_point,
            confidence=top_score,
            candidates_count=len(scored_matches),
            top_candidates=scored_matches[:3],
        )

    def _gather_candidates(self, tree: UITree, query: TargetQuery) -> list[UIElement]:
        """
        Gathers raw candidates from tree filtering out irrelevant scopes.
        """
        candidates: list[UIElement] = []

        # Target type preference
        target_type = query.semantic_type or ElementType.VIDEO_CARD

        for elem in tree.elements.values():
            # Exclude browser chrome when querying webpage
            if elem.scope == "BROWSER_CHROME" and query.region_type != RegionType.BROWSER_CHROME:
                continue

            # Section filter
            if query.section_name:
                elem_sec = (elem.section_id or "").upper()
                if query.section_name.upper() not in elem_sec:
                    # Check container
                    cont = tree.get_container(elem.container_id or "")
                    if not cont or query.section_name.upper() not in cont.section_name.upper():
                        continue

            # Semantic type match
            if query.semantic_type:
                if elem.type == target_type:
                    candidates.append(elem)
                elif query.semantic_type == ElementType.VIDEO_CARD and elem.type in (ElementType.VIDEO, ElementType.VIDEO_CARD):
                    candidates.append(elem)
                elif query.semantic_type in (ElementType.SEARCH_INPUT, ElementType.SEARCH_BUTTON) and elem.type in (ElementType.INPUT, ElementType.SEARCH_INPUT, ElementType.BUTTON, ElementType.SEARCH_BUTTON):
                    candidates.append(elem)
                elif query.semantic_type == ElementType.BUTTON and elem.clickable:
                    candidates.append(elem)
            else:
                # Default: include interactive elements and composite roots
                if elem.clickable or elem.type in (ElementType.VIDEO_CARD, ElementType.PLAYLIST_ITEM, ElementType.SHORT_CARD, ElementType.SIDEBAR_ITEM):
                    candidates.append(elem)

        return candidates

    def _score_candidate(
        self,
        elem: UIElement,
        comp: Optional[CompositeComponent],
        query: TargetQuery,
        tree: UITree,
    ) -> CandidateMatch:
        """
        Score candidate across semantic, text, ordinal, container, row/col, and spatial metrics.
        """
        match = CandidateMatch(element=elem, composite=comp)

        # 1. Semantic Match Score [0.0 - 1.0]
        if query.semantic_type:
            if elem.type == query.semantic_type:
                match.semantic_score = 1.0
            elif query.semantic_type == ElementType.VIDEO_CARD and elem.type == ElementType.VIDEO:
                match.semantic_score = 0.95
            else:
                match.semantic_score = 0.60
        else:
            match.semantic_score = 0.80

        # 2. Ordinal / Visual Index Match Score [0.0 - 1.0]
        if query.ordinal_index is not None:
            elem_v_idx = elem.visual_index
            if elem_v_idx < 0 and elem.visual_ordinal > 0:
                elem_v_idx = elem.visual_ordinal - 1
            if comp and comp.visual_index >= 0:
                elem_v_idx = comp.visual_index

            if elem_v_idx == query.ordinal_index:
                match.ordinal_score = 1.0
            else:
                dist = abs(elem_v_idx - query.ordinal_index)
                match.ordinal_score = max(0.0, 1.0 - (dist * 0.40))
        else:
            match.ordinal_score = 0.80

        # 3. Row & Column Match Score [0.0 - 1.0]
        row_col_score = 1.0
        if query.row is not None:
            elem_row = elem.row if elem.row >= 0 else (comp.row if comp else -1)
            row_col_score *= (1.0 if elem_row == query.row else 0.0)

        if query.column is not None:
            elem_col = elem.column if elem.column >= 0 else (comp.column if comp else -1)
            row_col_score *= (1.0 if elem_col == query.column else 0.0)

        # 4. Text / Substring Match Score [0.0 - 1.0]
        if query.text_pattern:
            target_text = query.text_pattern.lower()
            elem_text = (elem.text or elem.normalized_text or "").lower()
            if comp and comp.title and comp.title.text:
                elem_text = f"{elem_text} {comp.title.text.lower()}"

            if target_text in elem_text:
                match.text_score = 1.0
            else:
                # Substring token overlap
                q_words = set(target_text.split())
                e_words = set(elem_text.split())
                overlap = len(q_words & e_words)
                match.text_score = overlap / len(q_words) if q_words else 0.0
        else:
            match.text_score = 0.80

        # 5. Spatial Relation Score [0.0 - 1.0]
        if query.spatial_relation and query.anchor_query:
            anchor_elem = self._find_anchor_element(tree, query.anchor_query)
            if anchor_elem:
                is_rel = self.spatial_reasoner.evaluate_relation(elem, anchor_elem, query.spatial_relation)
                match.spatial_score = 1.0 if is_rel else 0.1
            else:
                match.spatial_score = 0.5
        else:
            match.spatial_score = 1.0

        # 6. Container / Section Match
        if query.section_name:
            sec_name = query.section_name.upper()
            elem_sec = (elem.section_id or "").upper()
            match.container_score = 1.0 if sec_name in elem_sec else 0.2
        else:
            match.container_score = 1.0

        # Weighted Total Score
        # If ordinal was explicitly requested, ordinal_score has the highest weight!
        if query.ordinal_index is not None:
            total = (
                match.semantic_score * 0.25
                + match.ordinal_score * 0.45
                + row_col_score * 0.15
                + match.text_score * 0.10
                + match.container_score * 0.05
            )
        elif query.text_pattern:
            total = (
                match.text_score * 0.50
                + match.semantic_score * 0.25
                + match.container_score * 0.15
                + match.spatial_score * 0.10
            )
        elif query.spatial_relation:
            total = (
                match.spatial_score * 0.50
                + match.semantic_score * 0.30
                + match.container_score * 0.20
            )
        else:
            total = (
                match.semantic_score * 0.35
                + row_col_score * 0.30
                + match.container_score * 0.20
                + match.text_score * 0.15
            )

        match.total_score = total
        return match

    def _find_anchor_element(self, tree: UITree, anchor_query: str) -> Optional[UIElement]:
        """Find the reference element for relative spatial queries."""
        q_low = anchor_query.lower()
        for elem in tree.elements.values():
            e_text = (elem.text or elem.normalized_text or "").lower()
            if q_low in e_text or q_low in elem.id.lower() or q_low in elem.semantic_role.lower():
                return elem
            if ("search" in q_low or "tìm kiếm" in q_low) and elem.type in (ElementType.SEARCH_INPUT, ElementType.INPUT):
                return elem
        return None

    def calculate_safe_interaction_point(
        self,
        element: UIElement,
        composite: Optional[CompositeComponent],
        child_type: Optional[ElementType],
        action: ActionType,
        tree: UITree,
    ) -> InteractionPoint:
        """
        Calculate precise, safe click coordinates inside target bbox.
        Enforces safe margin away from boundaries and unintended interactive sub-buttons.
        """
        target_bbox = element.bbox

        # 1. Resolve to preferred sub-component if applicable
        if child_type == ElementType.MORE_BUTTON and composite and composite.more_button:
            target_bbox = composite.more_button.bbox
            target_id = composite.more_button.id
            target_t = ElementType.MORE_BUTTON
        elif child_type == ElementType.TITLE and composite and composite.title:
            target_bbox = composite.title.bbox
            target_id = composite.title.id
            target_t = ElementType.TITLE
        elif child_type == ElementType.THUMBNAIL and composite and composite.thumbnail:
            target_bbox = composite.thumbnail.bbox
            target_id = composite.thumbnail.id
            target_t = ElementType.THUMBNAIL
        elif action in (ActionType.OPEN, ActionType.PLAY) and composite and composite.thumbnail:
            # For OPEN VIDEO, thumbnail center is the safest, most stable interaction region
            target_bbox = composite.thumbnail.bbox
            target_id = composite.thumbnail.id
            target_t = ElementType.THUMBNAIL
        else:
            target_id = element.id
            target_t = element.type

        # 2. Compute Center Point with Safe Margin in Viewport Space
        safe_x = target_bbox.center_x
        safe_y = target_bbox.center_y

        sw = max(1, tree.screen_width)
        sh = max(1, tree.screen_height)

        norm_x = safe_x / float(sw) if sw > 0 else 0.5
        norm_y = safe_y / float(sh) if sh > 0 else 0.5

        vp_coord = Coordinate(x=safe_x, y=safe_y, space=CoordinateSpace.VIEWPORT_SPACE)

        return InteractionPoint(
            pixel_x=int(round(safe_x)),
            pixel_y=int(round(safe_y)),
            normalized_x=norm_x,
            normalized_y=norm_y,
            target_element_id=target_id,
            target_type=target_t,
            action_type=action,
            is_safe=True,
            reason="Bounded center with margin",
            coordinate=vp_coord,
        )

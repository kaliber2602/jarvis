"""
Spatial Reasoning Engine.
Computes geometric relationships (Left Of, Right Of, Above, Below, Near, Inside, Overlaps)
and resolves directional queries between UI elements.
"""

from __future__ import annotations

import logging
import math
from typing import Optional, Sequence

from .models import BoundingBox, Point, SpatialRelation, UIElement

log = logging.getLogger("hermes_ui.spatial_reasoner")


class SpatialReasoner:
    """
    Evaluates relative spatial relationships and directional queries.
    """

    def __init__(self):
        pass

    def evaluate_relation(
        self,
        elem_a: UIElement,
        elem_b: UIElement,
        relation: SpatialRelation,
    ) -> bool:
        """
        Check if (elem_a <relation> elem_b) is true.
        For example: evaluate_relation(search_button, search_input, SpatialRelation.RIGHT_OF)
        """
        ba = elem_a.bbox
        bb = elem_b.bbox

        if relation == SpatialRelation.CONTAINS:
            return bb.contains_bbox(ba)

        elif relation == SpatialRelation.INSIDE:
            return ba.contains_bbox(bb)

        elif relation == SpatialRelation.OVERLAPS:
            return ba.overlaps(bb)

        elif relation == SpatialRelation.RIGHT_OF:
            # A must be to the right of B (a.left >= b.center_x), with vertical overlap or close Y alignment
            horizontal_valid = ba.left >= (bb.center_x - 10.0)
            vert_overlap = self.calculate_vertical_overlap(ba, bb)
            return horizontal_valid and (vert_overlap > 0.15 or abs(ba.center_y - bb.center_y) < max(ba.height, bb.height))

        elif relation == SpatialRelation.LEFT_OF:
            # A must be to the left of B (a.right <= b.center_x)
            horizontal_valid = ba.right <= (bb.center_x + 10.0)
            vert_overlap = self.calculate_vertical_overlap(ba, bb)
            return horizontal_valid and (vert_overlap > 0.15 or abs(ba.center_y - bb.center_y) < max(ba.height, bb.height))

        elif relation == SpatialRelation.BELOW:
            # A must be below B (a.top >= b.center_y), with horizontal overlap
            vert_valid = ba.top >= (bb.center_y - 10.0)
            horiz_overlap = self.calculate_horizontal_overlap(ba, bb)
            return vert_valid and (horiz_overlap > 0.20 or abs(ba.center_x - bb.center_x) < max(ba.width, bb.width))

        elif relation == SpatialRelation.ABOVE:
            # A must be above B (a.bottom <= b.center_y)
            vert_valid = ba.bottom <= (bb.center_y + 10.0)
            horiz_overlap = self.calculate_horizontal_overlap(ba, bb)
            return vert_valid and (horiz_overlap > 0.20 or abs(ba.center_x - bb.center_x) < max(ba.width, bb.width))

        elif relation == SpatialRelation.NEAR:
            dist = ba.center.distance_to(bb.center)
            max_dim = max(ba.width, ba.height, bb.width, bb.height)
            return dist <= max_dim * 2.5

        elif relation == SpatialRelation.ADJACENT_TO:
            return self.is_adjacent(ba, bb)

        return False

    def calculate_horizontal_overlap(self, ba: BoundingBox, bb: BoundingBox) -> float:
        """Percentage of horizontal overlap between two boxes relative to min width."""
        x_left = max(ba.left, bb.left)
        x_right = min(ba.right, bb.right)
        overlap = max(0.0, x_right - x_left)
        min_w = min(ba.width, bb.width)
        return overlap / min_w if min_w > 0 else 0.0

    def calculate_vertical_overlap(self, ba: BoundingBox, bb: BoundingBox) -> float:
        """Percentage of vertical overlap between two boxes relative to min height."""
        y_top = max(ba.top, bb.top)
        y_bottom = min(ba.bottom, bb.bottom)
        overlap = max(0.0, y_bottom - y_top)
        min_h = min(ba.height, bb.height)
        return overlap / min_h if min_h > 0 else 0.0

    def is_adjacent(self, ba: BoundingBox, bb: BoundingBox, tolerance: float = 40.0) -> bool:
        """Check if two boxes are adjacent horizontally or vertically."""
        horiz_dist = max(0.0, max(ba.left - bb.right, bb.left - ba.right))
        vert_dist = max(0.0, max(ba.top - bb.bottom, bb.top - ba.bottom))

        horiz_adj = horiz_dist <= tolerance and self.calculate_vertical_overlap(ba, bb) > 0.2
        vert_adj = vert_dist <= tolerance and self.calculate_horizontal_overlap(ba, bb) > 0.2
        return horiz_adj or vert_adj

    def find_nearest_element(
        self,
        anchor: UIElement,
        candidates: Sequence[UIElement],
        relation: Optional[SpatialRelation] = None,
    ) -> Optional[tuple[UIElement, float]]:
        """
        Find the closest matching candidate in the given spatial direction.
        Returns (nearest_element, score).
        """
        if not candidates:
            return None

        best_elem: Optional[UIElement] = None
        best_dist = float("inf")

        for cand in candidates:
            if cand.id == anchor.id:
                continue

            if relation is not None:
                if not self.evaluate_relation(cand, anchor, relation):
                    continue

            dist = cand.bbox.center.distance_to(anchor.bbox.center)
            if dist < best_dist:
                best_dist = dist
                best_elem = cand

        if best_elem is not None:
            # Score decreases with distance [0.0 to 1.0]
            max_span = 1920.0
            score = max(0.0, 1.0 - (best_dist / max_span))
            return best_elem, score

        return None

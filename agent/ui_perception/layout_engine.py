"""
Layout Understanding, Adaptive Row Clustering, and Human-Like Visual Enumeration Engine.
Clusters elements into visual rows/columns and generates row-major visual indices.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

from .models import BoundingBox, LayoutType, UIContainer, UIElement

log = logging.getLogger("hermes_ui.layout_engine")


class LayoutEngine:
    """
    Infers layout topology, dynamically clusters visual rows, and produces
    natural row-major visual ordering for human-like enumeration.
    """

    def __init__(self):
        pass

    def infer_layout_type(self, elements: Sequence[UIElement]) -> LayoutType:
        """
        Infer the layout structure of a group of elements.
        """
        if not elements:
            return LayoutType.UNKNOWN
        if len(elements) == 1:
            return LayoutType.CARD_CONTAINER

        # Check if all elements share similar Y (single row) -> HORIZONTAL_LIST
        ys = [e.bbox.center_y for e in elements]
        xs = [e.bbox.center_x for e in elements]
        y_span = max(ys) - min(ys)
        x_span = max(xs) - min(xs)
        avg_h = sum(e.bbox.height for e in elements) / len(elements)
        avg_w = sum(e.bbox.width for e in elements) / len(elements)

        if y_span < avg_h * 0.4 and x_span > avg_w:
            return LayoutType.HORIZONTAL_LIST

        # Check if all elements share similar X (single column) -> VERTICAL_LIST
        if x_span < avg_w * 0.4 and y_span > avg_h:
            return LayoutType.VERTICAL_LIST

        # Multi-row, multi-column -> GRID
        return LayoutType.GRID

    def cluster_into_visual_rows(
        self,
        elements: Sequence[UIElement],
        y_tolerance_ratio: float = 0.4,
    ) -> list[list[UIElement]]:
        """
        Adaptive Row Clustering Algorithm.
        Groups elements into visual rows based on adaptive vertical overlap and geometry.
        Does NOT rely on fixed hardcoded pixel thresholds.
        """
        if not elements:
            return []

        # Sort initially by top Y to process downwards
        sorted_by_y = sorted(elements, key=lambda e: (e.bbox.top, e.bbox.left))

        # Calculate adaptive Y tolerance based on median element height
        heights = sorted([e.bbox.height for e in elements if e.bbox.height > 0])
        median_height = heights[len(heights) // 2] if heights else 50.0
        y_tolerance = max(8.0, median_height * y_tolerance_ratio)

        rows: list[list[UIElement]] = []
        row_centers_y: list[float] = []

        for elem in sorted_by_y:
            elem_center_y = elem.bbox.center_y
            elem_top = elem.bbox.top

            # Find matching row cluster
            matched_row_idx = -1
            min_dist = float("inf")

            for r_idx, r_center in enumerate(row_centers_y):
                dist = abs(elem_center_y - r_center)
                if dist < y_tolerance and dist < min_dist:
                    min_dist = dist
                    matched_row_idx = r_idx

            if matched_row_idx >= 0:
                # Add to existing row and update average row center
                rows[matched_row_idx].append(elem)
                row_elems = rows[matched_row_idx]
                row_centers_y[matched_row_idx] = sum(e.bbox.center_y for e in row_elems) / len(row_elems)
            else:
                # Create a new visual row
                rows.append([elem])
                row_centers_y.append(elem_center_y)

        # Sort each row by X (left -> right)
        for row in rows:
            row.sort(key=lambda e: e.bbox.left)

        # Sort all rows by their average Y (top -> bottom)
        combined = list(zip(rows, row_centers_y))
        combined.sort(key=lambda pair: pair[1])
        sorted_rows = [pair[0] for pair in combined]

        return sorted_rows

    def apply_row_major_ordering(
        self,
        elements: Sequence[UIElement],
        container: Optional[UIContainer] = None,
        exclude_ads_from_visual_index: bool = False,
    ) -> list[UIElement]:
        """
        Performs complete Row-Major Visual Ordering:
        1. Cluster elements into adaptive visual rows.
        2. Sort elements within each row from Left -> Right.
        3. Sort rows from Top -> Bottom.
        4. Assign (row, column) and visual_index to each element.
        5. Returns flattened list in natural reading / visual order.
        """
        if not elements:
            return []

        rows = self.cluster_into_visual_rows(elements)
        flattened: list[UIElement] = []
        visual_idx_counter = 0

        max_cols = max((len(r) for r in rows), default=0)

        for r_idx, row in enumerate(rows):
            for c_idx, elem in enumerate(row):
                elem.row = r_idx
                elem.column = c_idx
                if container:
                    elem.container_id = container.id
                    elem.region_id = container.region_id

                # Assign visual index (skipping ads if configured)
                if exclude_ads_from_visual_index and elem.is_advertisement:
                    elem.visual_index = -1
                else:
                    elem.visual_index = visual_idx_counter
                    visual_idx_counter += 1

                flattened.append(elem)

        if container:
            container.rows_count = len(rows)
            container.columns_count = max_cols
            container.element_ids = [e.id for e in flattened]

        log.debug(
            "[LAYOUT_ENGINE] Ordered %d elements across %d rows and %d max cols (Visual count: %d)",
            len(flattened), len(rows), max_cols, visual_idx_counter
        )
        return flattened

    def organize_container_elements(
        self,
        container: UIContainer,
        elements: Sequence[UIElement],
    ) -> list[UIElement]:
        """
        Organize and index all elements within a specific container according to its layout type.
        """
        if not elements:
            return []

        layout = container.layout_type
        if layout == LayoutType.UNKNOWN:
            layout = self.infer_layout_type(elements)
            container.layout_type = layout

        if layout in (LayoutType.VERTICAL_LIST, LayoutType.SIDEBAR):
            # Pure vertical sort
            sorted_elems = sorted(elements, key=lambda e: e.bbox.top)
            for idx, elem in enumerate(sorted_elems):
                elem.row = idx
                elem.column = 0
                elem.container_id = container.id
                elem.region_id = container.region_id
                elem.visual_index = idx
            container.rows_count = len(sorted_elems)
            container.columns_count = 1
            container.element_ids = [e.id for e in sorted_elems]
            return sorted_elems

        elif layout in (LayoutType.HORIZONTAL_LIST, LayoutType.NAVBAR, LayoutType.CAROUSEL):
            # Pure horizontal sort
            sorted_elems = sorted(elements, key=lambda e: e.bbox.left)
            for idx, elem in enumerate(sorted_elems):
                elem.row = 0
                elem.column = idx
                elem.container_id = container.id
                elem.region_id = container.region_id
                elem.visual_index = idx
            container.rows_count = 1
            container.columns_count = len(sorted_elems)
            container.element_ids = [e.id for e in sorted_elems]
            return sorted_elems

        else:
            # Standard 2D Grid / Card Container
            return self.apply_row_major_ordering(elements, container=container)

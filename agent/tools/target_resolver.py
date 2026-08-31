"""
Target Resolver: Pure Semantic Target Resolution & Natural Reading Order Subsystem.
Transforms high-level semantic queries (e.g., 'chọn video thứ 2', index=2) into concrete UIComponents.
Strictly decoupled from Interaction execution (DOES NOT PERFORM ANY CLICKS).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .interaction_models import ComponentSource, ErrorCode, UIComponent

log = logging.getLogger("hermes.target_resolver")


@dataclass
class TargetResolutionResult:
    """Outcome of pure target resolution."""
    target: Optional[UIComponent] = None
    ordered_candidates: list[UIComponent] = field(default_factory=list)
    semantic_index: int = 1
    total_detected: int = 0
    confidence: float = 1.0
    error_code: Optional[ErrorCode] = None
    error_message: str = ""

    @property
    def is_success(self) -> bool:
        return self.target is not None and self.error_code is None


class TargetResolver:
    """
    Pure Target Resolution Engine.
    Implements Adaptive Row Clustering and Human Natural Reading Order (Top -> Bottom, Left -> Right).
    """

    ORDINAL_MAP: dict[str, int] = {
        "đầu tiên": 1, "dau tien": 1, "first": 1, "1st": 1, "1": 1, "một": 1, "mot": 1, "one": 1,
        "thứ nhất": 1, "thu nhat": 1, "thứ 1": 1, "thu 1": 1, "item 1": 1, "video 1": 1,
        "thứ hai": 2, "thu hai": 2, "second": 2, "2nd": 2, "2": 2, "hai": 2, "two": 2,
        "thứ 2": 2, "thu 2": 2, "item 2": 2, "video 2": 2,
        "thứ ba": 3, "thu ba": 3, "third": 3, "3rd": 3, "3": 3, "ba": 3, "three": 3,
        "thứ 3": 3, "thu 3": 3, "item 3": 3, "video 3": 3,
        "thứ bốn": 4, "thu bon": 4, "thứ tư": 4, "thu tu": 4, "fourth": 4, "4th": 4, "4": 4, "bốn": 4, "bon": 4, "tư": 4, "tu": 4, "four": 4,
        "thứ 4": 4, "thu 4": 4, "item 4": 4, "video 4": 4,
        "thứ năm": 5, "thu nam": 5, "fifth": 5, "5th": 5, "5": 5, "năm": 5, "nam": 5, "five": 5,
        "thứ 5": 5, "thu 5": 5, "item 5": 5, "video 5": 5,
        "thứ sáu": 6, "thu sau": 6, "sixth": 6, "6th": 6, "6": 6, "sáu": 6, "sau": 6, "six": 6,
        "thứ 6": 6, "thu 6": 6, "item 6": 6, "video 6": 6,
        "thứ bảy": 7, "thu bay": 7, "seventh": 7, "7th": 7, "7": 7, "bảy": 7, "bay": 7, "seven": 7,
        "thứ 7": 7, "thu 7": 7, "item 7": 7, "video 7": 7,
        "thứ tám": 8, "thu tam": 8, "eighth": 8, "8th": 8, "8": 8, "tám": 8, "tam": 8, "eight": 8,
        "thứ 8": 8, "thu 8": 8, "item 8": 8, "video 8": 8,
        "thứ chín": 9, "thu chin": 9, "ninth": 9, "9th": 9, "9": 9, "chín": 9, "chin": 9, "nine": 9,
        "thứ 9": 9, "thu 9": 9, "item 9": 9, "video 9": 9,
        "thứ mười": 10, "thu muoi": 10, "tenth": 10, "10th": 10, "10": 10, "mười": 10, "muoi": 10, "ten": 10,
        "thứ 10": 10, "thu 10": 10, "item 10": 10, "video 10": 10,
    }

    @classmethod
    def parse_semantic_index(cls, query_text: str, default_index: int = 1) -> int:
        """Extract requested 1-based semantic index from natural language utterance."""
        q_low = (query_text or "").strip().lower()
        for phrase, idx_val in cls.ORDINAL_MAP.items():
            pattern = r"\b" + re.escape(phrase) + r"\b"
            if re.search(pattern, q_low):
                return idx_val

        # Numeric fallback: "thứ 2", "#3", "số 4", "video 2"
        m = re.search(r"(?:thứ|thu|số|so|#|number|video|clip|bài|bai)\s*(\d+)", q_low)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        return default_index

    @classmethod
    def cluster_by_y(
        cls,
        components: Sequence[UIComponent],
        y_tolerance_ratio: float = 0.4,
    ) -> list[list[UIComponent]]:
        """
        Adaptive Row Clustering.
        Groups components into rows based on adaptive vertical overlap and median height.
        Does NOT rely on fixed hardcoded pixel thresholds.
        """
        if not components:
            return []

        # Sort initially by top Y to process downwards
        sorted_by_y = sorted(components, key=lambda c: (c.top, c.left))

        heights = sorted([c.height for c in components if c.height > 0])
        median_height = heights[len(heights) // 2] if heights else 50.0
        y_tolerance = max(8.0, median_height * y_tolerance_ratio)

        rows: list[list[UIComponent]] = []
        row_centers_y: list[float] = []

        for comp in sorted_by_y:
            c_y = comp.center_y
            matched_row_idx = -1
            min_dist = float("inf")

            for r_idx, r_center in enumerate(row_centers_y):
                dist = abs(c_y - r_center)
                if dist < y_tolerance and dist < min_dist:
                    min_dist = dist
                    matched_row_idx = r_idx

            if matched_row_idx >= 0:
                rows[matched_row_idx].append(comp)
                row_comps = rows[matched_row_idx]
                row_centers_y[matched_row_idx] = sum(c.center_y for c in row_comps) / len(row_comps)
            else:
                rows.append([comp])
                row_centers_y.append(c_y)

        # Sort elements in each row from Left -> Right by center_x / left
        for row in rows:
            row.sort(key=lambda c: c.center_x)

        # Sort all rows from Top -> Bottom by average center_y
        combined = list(zip(rows, row_centers_y))
        combined.sort(key=lambda pair: pair[1])
        sorted_rows = [pair[0] for pair in combined]

        return sorted_rows

    @classmethod
    def apply_natural_reading_order(
        cls,
        components: Sequence[UIComponent],
        y_tolerance_ratio: float = 0.4,
    ) -> list[UIComponent]:
        """
        Produce human Natural Reading Order (Top -> Bottom, Left -> Right).
        Annotates row, column, and visual index on each component.
        """
        if not components:
            return []

        rows = cls.cluster_by_y(components, y_tolerance_ratio=y_tolerance_ratio)
        ordered: list[UIComponent] = []

        for r_idx, row in enumerate(rows):
            for c_idx, comp in enumerate(row):
                comp.row = r_idx
                comp.column = c_idx
                ordered.append(comp)

        return ordered

    @classmethod
    def resolve(
        cls,
        components: Sequence[UIComponent],
        component_type: str = "video",
        index: int = 1,
        query: str = "",
    ) -> TargetResolutionResult:
        """
        Pure Target Resolution:
        Filters matching components, orders them via Natural Reading Order,
        and selects the element matching the requested semantic index (1-based).
        """
        semantic_idx = index
        if query:
            semantic_idx = cls.parse_semantic_index(query, default_index=index)

        # Filter by component type if specified
        c_type_low = component_type.lower()
        candidates = [
            c for c in components
            if not c_type_low or c_type_low in c.type.lower() or c_type_low in c.id.lower()
        ]

        if not candidates:
            # Fallback to all components if specific type has no match
            candidates = list(components)

        log.info(
            "[UI TARGET DISCOVERY] source=%s count=%d",
            candidates[0].source.value if candidates else "UNKNOWN",
            len(candidates),
        )

        if not candidates:
            log.warning("[TARGET RESOLUTION] Error: No candidates found.")
            return TargetResolutionResult(
                target=None,
                ordered_candidates=[],
                semantic_index=semantic_idx,
                total_detected=0,
                error_code=ErrorCode.TARGET_NOT_FOUND,
                error_message="No interactive UI components found.",
            )

        # Apply Natural Reading Order
        ordered = cls.apply_natural_reading_order(candidates)

        if semantic_idx < 1 or semantic_idx > len(ordered):
            log.warning(
                "[TARGET RESOLUTION] Requested index=%d outside range (1..%d)",
                semantic_idx, len(ordered)
            )
            return TargetResolutionResult(
                target=None,
                ordered_candidates=ordered,
                semantic_index=semantic_idx,
                total_detected=len(ordered),
                error_code=ErrorCode.TARGET_NOT_FOUND,
                error_message=f"Target index {semantic_idx} not found (only {len(ordered)} candidates detected).",
            )

        target = ordered[semantic_idx - 1]

        # Structured Logging per Specification
        log.info(
            "[TARGET RESOLUTION]\nrequested='%s'\nsemantic_index=%d\nresolved_component=%s",
            query or f"{component_type} #{semantic_idx}",
            semantic_idx,
            target.id,
        )
        log.info(
            "[TARGET BBOX]\nx=%.1f\ny=%.1f\nwidth=%.1f\nheight=%.1f",
            target.left, target.top, target.width, target.height,
        )
        log.info("[TARGET SOURCE]\n%s", target.source.value)

        return TargetResolutionResult(
            target=target,
            ordered_candidates=ordered,
            semantic_index=semantic_idx,
            total_detected=len(ordered),
            confidence=target.confidence,
        )

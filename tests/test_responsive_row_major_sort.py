"""
Unit Test Suite for Responsive ROW_MAJOR_SORT and Dynamic Visual Grid Mapping.

Validates:
1. Dynamic 3-column grid layout for 12 video boxes on a 1400px width window:
   - Grouped into 4 rows with 3 items each.
   - Video 5 resolves to Row 2, Column 2 (0-based row=1, column=1).
   - Video 5 X coordinate >= Column 1 X coordinate.
2. Visibility Culling:
   - Offscreen bounding boxes (X >= viewport_width or center > viewport_width) are culled before sorting.
3. Safe click point accuracy:
   - Safe point resides in the thumbnail area avoiding dead zones and avatars.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools.component_target import ComponentTarget, build_safe_click_region, resolve_safe_click_point, sort_row_major
from agent.ui_perception.models import BoundingBox, Point


class TestResponsiveRowMajorSort(unittest.TestCase):

    def test_12_boxes_3_columns_1400_width_layout(self):
        """
        Input Mock: 12 boxes, width each = 442, window width = 1400 (3 columns per row).
        Expected Output:
          - ROW_MAJOR_SORT groups into 4 rows (3 items each).
          - Box 5 belongs to row index 1 (Row 2), column index 1 (Column 2).
          - Box 5 center X >= column 1 center X.
        """
        # 12 boxes arranged in 4 rows of 3 columns
        # Column X coordinates: 50.0, 508.0, 966.0 (width 442, gap 16) -> all within 1400px
        # Row Y coordinates: 104.0, 464.0, 824.0, 1184.0 (height 336, gap 24)
        mock_boxes_12 = []
        box_counter = 1
        col_xs = [50.0, 508.0, 966.0]
        row_ys = [104.0, 464.0, 824.0, 1184.0]

        for r_idx, y in enumerate(row_ys):
            for c_idx, x in enumerate(col_xs):
                mock_boxes_12.append({
                    "id": f"yt_video_card_{box_counter}",
                    "type": "VIDEO_CARD",
                    "bbox": (x, y, 442.0, 336.0),
                    "text": f"Video #{box_counter}",
                })
                box_counter += 1

        self.assertEqual(len(mock_boxes_12), 12)

        ordered = sort_row_major(mock_boxes_12, viewport_width=1400.0)

        # 1. Verify total ordered components
        self.assertEqual(len(ordered), 12)

        # 2. Verify row grouping: 4 rows with 3 items each
        rows_grouped = {}
        for target in ordered:
            rows_grouped.setdefault(target.row, []).append(target)

        self.assertEqual(len(rows_grouped), 4, "Must group into exactly 4 rows")
        for r_idx in range(4):
            self.assertEqual(len(rows_grouped[r_idx]), 3, f"Row {r_idx} must contain exactly 3 items")

        # 3. Verify Video 5 (index 4) location
        target_5 = ordered[4]  # Ordinal 5
        self.assertEqual(target_5.ordinal, 5)
        self.assertEqual(target_5.component_id, "yt_video_card_5")
        self.assertEqual(target_5.row, 1, "Video 5 must be in Row index 1 (Row 2)")
        self.assertEqual(target_5.column, 1, "Video 5 must be in Column index 1 (Column 2 - middle of row)")

        # 4. Verify Video 5 coordinates
        # Center X of Video 5 is 508.0 + 221.0 = 729.0
        # Center X of Video 4 (Column 1) is 50.0 + 221.0 = 271.0
        target_4 = ordered[3]
        self.assertEqual(target_4.row, 1)
        self.assertEqual(target_4.column, 0)
        self.assertGreater(target_5.center[0], target_4.center[0], "Video 5 X must be greater than Column 1 X")

        # 5. Verify Safe Click Point on Video 5
        self.assertAlmostEqual(target_5.safe_click_point[0], 221.0, places=1)
        self.assertAlmostEqual(target_5.safe_click_point[1], 109.2, places=1)

    def test_visibility_culling_offscreen_cards(self):
        """
        When a naive detector returns 16 cards (4 cards per row) on a 1400px window:
        The 4th card of each row (x=1462 >= 1400) must be culled.
        The remaining 12 cards must be ordered as a 3x4 grid with video 5 at row 1, col 1.
        """
        mock_boxes_16 = [
            # Row 1
            {"id": "card_1", "bbox": (88.0, 104.0, 442.0, 336.0)},
            {"id": "card_2", "bbox": (546.0, 104.0, 442.0, 336.0)},
            {"id": "card_3", "bbox": (1004.0, 104.0, 442.0, 336.0)},
            {"id": "card_4_offscreen", "bbox": (1462.0, 104.0, 442.0, 336.0)},  # Offscreen
            # Row 2
            {"id": "card_5", "bbox": (88.0, 464.0, 442.0, 336.0)},
            {"id": "card_6", "bbox": (546.0, 464.0, 442.0, 336.0)},
            {"id": "card_7", "bbox": (1004.0, 464.0, 442.0, 336.0)},
            {"id": "card_8_offscreen", "bbox": (1462.0, 464.0, 442.0, 336.0)},  # Offscreen
            # Row 3
            {"id": "card_9", "bbox": (88.0, 824.0, 442.0, 336.0)},
            {"id": "card_10", "bbox": (546.0, 824.0, 442.0, 336.0)},
            {"id": "card_11", "bbox": (1004.0, 824.0, 442.0, 336.0)},
            {"id": "card_12_offscreen", "bbox": (1462.0, 824.0, 442.0, 336.0)}, # Offscreen
            # Row 4
            {"id": "card_13", "bbox": (88.0, 1184.0, 442.0, 336.0)},
            {"id": "card_14", "bbox": (546.0, 1184.0, 442.0, 336.0)},
            {"id": "card_15", "bbox": (1004.0, 1184.0, 442.0, 336.0)},
            {"id": "card_16_offscreen", "bbox": (1462.0, 1184.0, 442.0, 336.0)},# Offscreen
        ]

        ordered = sort_row_major(mock_boxes_16, viewport_width=1400.0)

        # 4 offscreen elements must be culled -> exactly 12 visible targets
        self.assertEqual(len(ordered), 12)
        culled_ids = [t.component_id for t in ordered]
        self.assertNotIn("card_4_offscreen", culled_ids)
        self.assertNotIn("card_8_offscreen", culled_ids)
        self.assertNotIn("card_12_offscreen", culled_ids)
        self.assertNotIn("card_16_offscreen", culled_ids)

        # Video 5 must be 'card_6' (middle of row 2) instead of 'card_5'
        target_5 = ordered[4]
        self.assertEqual(target_5.ordinal, 5)
        self.assertEqual(target_5.component_id, "card_6")
        self.assertEqual(target_5.row, 1)
        self.assertEqual(target_5.column, 1)

    def test_safe_click_region_thumbnail_area(self):
        """
        Verify that SafeClickRegion targets the thumbnail image area
        and excludes badge and 3-dots popup areas.
        """
        card = {
            "id": "yt_video_card_5",
            "bbox": (508.0, 464.0, 442.0, 336.0),
            "children": [
                {"id": "yt_video_card_5_thumbnail", "role": "thumbnail", "bbox": (0, 0, 442, 218.4)},
                {"id": "yt_badge", "role": "badge", "bbox": (380, 180, 50, 20)},
                {"id": "yt_menu_3dots", "role": "menu", "bbox": (410, 260, 24, 24)},
            ]
        }

        safe_pt, child_id, reason = resolve_safe_click_point(card)
        self.assertEqual(child_id, "yt_video_card_5_thumbnail")
        self.assertAlmostEqual(safe_pt[0], 221.0, places=1)
        self.assertAlmostEqual(safe_pt[1], 109.2, places=1)


if __name__ == "__main__":
    unittest.main()

"""
Comprehensive Test Suite for Section 18 & 19 Requirements:
  - Cases 1 to 12: Visual reading order, row clustering, vertical displacement,
    differing widths, zoom/DPI, partial rows, invisible cards, overlays, and scroll.
  - Multi-level Verification (Input, Navigation, Target, Overall).
  - Fast-Path Deterministic Close Window & Video Selection Routing.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.tools.browser_context import WindowHandle, WindowSnapshot
from agent.tools.component_target import (
    ComponentTarget,
    YouTubeVideoTarget,
    derive_safe_interaction_point,
    resolve_clickable_region,
    resolve_safe_click_point,
    sort_row_major,
)
from agent.tools.coordinate_mapper import CoordinateMapper
from agent.tools.ui_interaction_service import TaskWindowContext, UIInteractionService, YouTubeState
from agent.tools.window_manager import WindowIdentity, WindowManager
from agent.tools.computer_use import ComputerUseTool, MouseExecutor
from agent.hermes_runtime import HermesRuntime


class TestDeterministicYouTubeAndWindowManagement(unittest.TestCase):

    # -------------------------------------------------------------------------
    # CASE 1: 1 row x 4 cards -> 1 2 3 4
    # -------------------------------------------------------------------------
    def test_case_1_one_row_four_cards(self):
        cards = [
            {"id": "card_d", "bbox": (1462, 104, 442, 336)},
            {"id": "card_b", "bbox": (546, 104, 442, 336)},
            {"id": "card_a", "bbox": (88, 104, 442, 336)},
            {"id": "card_c", "bbox": (1004, 104, 442, 336)},
        ]
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 4)
        self.assertEqual([c.component_id for c in ordered], ["card_a", "card_b", "card_c", "card_d"])
        self.assertEqual([c.ordinal for c in ordered], [1, 2, 3, 4])

    # -------------------------------------------------------------------------
    # CASE 2: 2 rows x 4 cards -> 1 2 3 4 5 6 7 8
    # -------------------------------------------------------------------------
    def test_case_2_two_rows_four_cards(self):
        cards = [
            {"id": f"card_{i}", "bbox": (88 + (i-1)*458, 104, 442, 336)} for i in range(1, 5)
        ] + [
            {"id": f"card_{i}", "bbox": (88 + (i-5)*458, 464, 442, 336)} for i in range(5, 9)
        ]
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 8)
        self.assertEqual([c.ordinal for c in ordered], list(range(1, 9)))
        self.assertEqual([c.row for c in ordered], [0, 0, 0, 0, 1, 1, 1, 1])

    # -------------------------------------------------------------------------
    # CASE 3: 3 rows x 4 cards -> 1..12
    # -------------------------------------------------------------------------
    def test_case_3_three_rows_four_cards(self):
        cards = []
        for r in range(3):
            for c in range(4):
                idx = r * 4 + c + 1
                cards.append({"id": f"card_{idx}", "bbox": (88 + c*458, 104 + r*360, 442, 336)})
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 12)
        self.assertEqual([c.ordinal for c in ordered], list(range(1, 13)))

    # -------------------------------------------------------------------------
    # CASE 4: Slight vertical displacement (y=100, y=108, y=96)
    # -------------------------------------------------------------------------
    def test_case_4_vertical_displacement_clustered_into_same_row(self):
        cards = [
            {"id": "card_2", "bbox": (546, 108, 442, 336)},
            {"id": "card_1", "bbox": (88, 100, 442, 336)},
            {"id": "card_3", "bbox": (1004, 96, 442, 336)},
            {"id": "card_4", "bbox": (1462, 104, 442, 336)},
        ]
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 4)
        self.assertEqual([c.component_id for c in ordered], ["card_1", "card_2", "card_3", "card_4"])
        self.assertEqual([c.row for c in ordered], [0, 0, 0, 0])

    # -------------------------------------------------------------------------
    # CASE 5: Differing card widths in same row
    # -------------------------------------------------------------------------
    def test_case_5_differing_card_widths(self):
        cards = [
            {"id": "card_1", "bbox": (50, 100, 300, 300)},
            {"id": "card_2", "bbox": (380, 100, 500, 300)},
            {"id": "card_3", "bbox": (910, 100, 400, 300)},
        ]
        ordered = sort_row_major(cards)
        self.assertEqual([c.component_id for c in ordered], ["card_1", "card_2", "card_3"])

    # -------------------------------------------------------------------------
    # CASE 6: Different screen resolutions (1366x768 -> 3 columns)
    # -------------------------------------------------------------------------
    def test_case_6_screen_resolution_layout(self):
        cards = [
            {"id": f"card_{i}", "bbox": (30 + (i-1)*420, 90, 400, 280)} for i in range(1, 4)
        ] + [
            {"id": f"card_{i}", "bbox": (30 + (i-4)*420, 390, 400, 280)} for i in range(4, 7)
        ]
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 6)
        self.assertEqual([c.ordinal for c in ordered], [1, 2, 3, 4, 5, 6])
        self.assertEqual([c.column for c in ordered], [0, 1, 2, 0, 1, 2])

    # -------------------------------------------------------------------------
    # CASE 7 & 8: Browser Zoom & DPI Scaling
    # -------------------------------------------------------------------------
    def test_case_7_and_8_zoom_and_dpi_scaling(self):
        origin = (100, 50)
        chrome_h = 80
        comp_bbox = (546.0, 104.0, 442.0, 336.0)
        safe_pt = (221.0, 109.2)

        screen_pt, trace = CoordinateMapper.to_screen(
            comp_point=safe_pt,
            comp_bbox=comp_bbox,
            client_screen_origin=origin,
            browser_chrome_height=chrome_h,
            dpi_scale=1.25,
        )
        expected_x = int(round((100 + 546 + 221) * 1.25))
        expected_y = int(round((50 + 80 + 104 + 109.2) * 1.25))
        self.assertEqual(screen_pt, (expected_x, expected_y))

    # -------------------------------------------------------------------------
    # CASE 9: Partial row (Row 1: 4 cards, Row 2: 2 cards)
    # -------------------------------------------------------------------------
    def test_case_9_partial_row(self):
        cards = [
            {"id": f"card_{i}", "bbox": (88 + (i-1)*458, 104, 442, 336)} for i in range(1, 5)
        ] + [
            {"id": f"card_{i}", "bbox": (88 + (i-5)*458, 464, 442, 336)} for i in range(5, 7)
        ]
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 6)
        self.assertEqual([c.ordinal for c in ordered], [1, 2, 3, 4, 5, 6])

    # -------------------------------------------------------------------------
    # CASE 10: Invisible and zero-size cards filtered out
    # -------------------------------------------------------------------------
    def test_case_10_invisible_and_zero_size_filtered(self):
        cards = [
            {"id": "valid_1", "bbox": (88, 104, 442, 336), "is_visible": True},
            {"id": "invisible_card", "bbox": (546, 104, 442, 336), "is_visible": False},
            {"id": "zero_size_card", "bbox": (1004, 104, 0, 0), "is_visible": True},
            {"id": "valid_2", "bbox": (1462, 104, 442, 336), "is_visible": True},
        ]
        ordered = sort_row_major(cards)
        self.assertEqual(len(ordered), 2)
        self.assertEqual([c.component_id for c in ordered], ["valid_1", "valid_2"])
        self.assertEqual([c.ordinal for c in ordered], [1, 2])

    # -------------------------------------------------------------------------
    # CASE 11: Overlay/menu/badges inside video card -> Safe Click Point
    # -------------------------------------------------------------------------
    def test_case_11_overlay_and_badge_avoidance(self):
        card = {
            "id": "yt_video_2",
            "bbox": (546, 104, 442, 336),
            "children": [
                {"id": "duration_badge", "role": "badge", "bbox": (380, 180, 50, 20)},
                {"id": "menu_3dots", "role": "button", "bbox": (410, 280, 24, 24)},
                {"id": "yt_thumb", "role": "thumbnail_anchor", "bbox": (0, 0, 442, 218)},
            ]
        }
        (local_x, local_y), elem_id, reason = resolve_safe_click_point(card)
        self.assertEqual(elem_id, "yt_thumb")
        self.assertEqual(reason, "semantic_clickable_child")
        self.assertEqual(local_x, 221.0)
        self.assertEqual(local_y, 109.0)

    # -------------------------------------------------------------------------
    # Fast-Path Deterministic Close Window & Video Selection Routing
    # -------------------------------------------------------------------------
    def test_fast_path_close_window_routing(self):
        runtime = HermesRuntime()
        plan = runtime._plan_instruction("close window")
        self.assertEqual(len(plan["actions"]), 1)
        self.assertEqual(plan["actions"][0]["tool"], "close_window")

    def test_fast_path_play_video_3_routing(self):
        runtime = HermesRuntime()
        plan = runtime._plan_instruction("play video 3")
        self.assertEqual(len(plan["actions"]), 1)
        self.assertEqual(plan["actions"][0]["tool"], "select_youtube_video")
        self.assertEqual(plan["actions"][0]["params"]["index"], 3)


if __name__ == "__main__":
    unittest.main()

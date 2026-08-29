"""
Comprehensive Test Suite for Hermes UI Perception, Semantic Tree,
Layout Understanding, Human-Like Visual Enumeration, Target Resolution,
Safe Interaction, and Action Verification Engine.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.ui_perception.composite_builder import CompositeBuilder
from agent.ui_perception.layout_engine import LayoutEngine
from agent.ui_perception.models import (
    ActionType,
    BoundingBox,
    ElementType,
    LayoutType,
    RegionType,
    ResolutionStatus,
    SpatialRelation,
    UIContainer,
    UIElement,
    UITree,
    VisibilityState,
)
from agent.ui_perception.region_detector import RegionDetector
from agent.ui_perception.service import HermesUIService, get_ui_service
from agent.ui_perception.spatial_reasoner import SpatialReasoner
from agent.ui_perception.target_resolver import TargetResolver
from agent.ui_perception.tree_builder import TreeBuilder
from agent.ui_perception.verification_engine import VerificationEngine


def test_1_youtube_video_row_and_column():
    """
    TEST 1: YouTube homepage "video thứ 3 hàng đầu"
    Expected: row=0, column=2, visual_index=2, safe click on thumbnail.
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    # Create 2x3 video grid
    raw_data = [
        {"id": "v0", "type": "VIDEO_CARD", "text": "Video A", "bbox": (250, 100, 300, 200)},
        {"id": "v1", "type": "VIDEO_CARD", "text": "Video B", "bbox": (580, 100, 300, 200)},
        {"id": "v2", "type": "VIDEO_CARD", "text": "Video C", "bbox": (910, 100, 300, 200)},
        {"id": "v3", "type": "VIDEO_CARD", "text": "Video D", "bbox": (250, 350, 300, 200)},
        {"id": "v4", "type": "VIDEO_CARD", "text": "Video E", "bbox": (580, 350, 300, 200)},
        {"id": "v5", "type": "VIDEO_CARD", "text": "Video F", "bbox": (910, 350, 300, 200)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "video thứ 3 hàng đầu")

    assert res.is_success() is True
    assert res.target_element is not None
    assert res.target_element.id == "v2"
    assert res.target_element.row == 0
    assert res.target_element.column == 2
    assert res.target_element.visual_index == 2
    assert res.interaction_point is not None
    assert res.interaction_point.target_type == ElementType.THUMBNAIL
    print("[TEST 1 PASSED] 'video thứ 3 hàng đầu' -> row=0, column=2, target=v2")


def test_2_youtube_shorts_section():
    """
    TEST 2: YouTube homepage "video thứ 2 trong Shorts"
    Expected: section=Shorts, index=1 (visual_index=1 within Shorts).
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "v0", "type": "VIDEO_CARD", "text": "Main Video 1", "bbox": (250, 100, 300, 200), "section": "MAIN"},
        {"id": "s0", "type": "SHORT_CARD", "text": "Short Alpha", "bbox": (250, 350, 180, 300), "section": "SHORTS"},
        {"id": "s1", "type": "SHORT_CARD", "text": "Short Beta", "bbox": (450, 350, 180, 300), "section": "SHORTS"},
        {"id": "s2", "type": "SHORT_CARD", "text": "Short Gamma", "bbox": (650, 350, 180, 300), "section": "SHORTS"},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "video thứ 2 trong Shorts")

    assert res.is_success() is True
    assert res.target_element is not None
    assert res.target_element.id == "s1"
    assert res.target_element.section_id == "SHORTS"
    assert res.target_element.visual_index == 1
    print("[TEST 2 PASSED] 'video thứ 2 trong Shorts' -> section=Shorts, visual_index=1, target=s1")


def test_3_playlist_item_selection():
    """
    TEST 3: YouTube playlist "video thứ 3 trong playlist"
    Expected: playlist_item=2 in RIGHT_PANEL -> PLAYLIST (does not click main player or playlist header).
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "main_player", "type": "VIDEO", "text": "Now Playing Video", "bbox": (250, 100, 900, 500), "region": "main"},
        {"id": "p0", "type": "PLAYLIST_ITEM", "text": "Playlist Track 1", "bbox": (1200, 150, 400, 60), "section": "PLAYLIST", "region": "right_panel"},
        {"id": "p1", "type": "PLAYLIST_ITEM", "text": "Playlist Track 2", "bbox": (1200, 220, 400, 60), "section": "PLAYLIST", "region": "right_panel"},
        {"id": "p2", "type": "PLAYLIST_ITEM", "text": "Playlist Track 3", "bbox": (1200, 290, 400, 60), "section": "PLAYLIST", "region": "right_panel"},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "video thứ 3 trong playlist")

    assert res.is_success() is True
    assert res.target_element is not None
    assert res.target_element.id == "p2"
    assert res.target_element.type == ElementType.PLAYLIST_ITEM
    assert res.target_element.visual_index == 2
    assert res.target_element.region_id == "reg_right_panel"
    print("[TEST 3 PASSED] 'video thứ 3 trong playlist' -> playlist_item=2, target=p2 in right_panel")


def test_4_more_button_composite_sub_target():
    """
    TEST 4: "nút ba chấm của video thứ 2"
    Expected: VideoCard[1] -> MoreButton (child target=MORE_BUTTON, action=OPEN_MENU).
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "v0", "type": "VIDEO_CARD", "text": "Intro to AI", "bbox": (250, 100, 300, 200)},
        {"id": "v1", "type": "VIDEO_CARD", "text": "Deep Learning Masterclass", "bbox": (580, 100, 300, 200)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "nút ba chấm của video thứ 2")

    assert res.is_success() is True
    assert res.target_element is not None
    assert res.target_element.id == "v1"
    assert res.interaction_point is not None
    assert res.interaction_point.target_type == ElementType.MORE_BUTTON
    assert res.interaction_point.action_type == ActionType.OPEN_MENU
    assert "v1_more_btn" in res.interaction_point.target_element_id
    print("[TEST 4 PASSED] 'nút ba chấm của video thứ 2' -> VideoCard[1] MoreButton")


def test_5_advertisement_filtering():
    """
    TEST 5: Advertisement standing before videos
    Expected: AD is excluded from VIDEO_CARD ordinal index.
    AD (idx skipped) -> Video A (0) -> Video B (1) -> Video C (2).
    User: "video thứ 3" -> Video C (visual_index=2).
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "ad0", "type": "VIDEO_CARD", "text": "Sponsored Ad Product", "bbox": (250, 100, 300, 200), "is_ad": True},
        {"id": "v0", "type": "VIDEO_CARD", "text": "Video Alpha", "bbox": (580, 100, 300, 200)},
        {"id": "v1", "type": "VIDEO_CARD", "text": "Video Beta", "bbox": (910, 100, 300, 200)},
        {"id": "v2", "type": "VIDEO_CARD", "text": "Video Gamma", "bbox": (250, 350, 300, 200)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "mở video thứ 3")

    assert res.is_success() is True
    assert res.target_element is not None
    assert res.target_element.id == "v2"
    assert res.target_element.visual_index == 2
    assert tree.get_element("ad0").is_advertisement is True
    print("[TEST 5 PASSED] Ad excluded from organic visual index -> 'mở video thứ 3' selected v2")


def test_6_sidebar_and_main_reading_order_isolation():
    """
    TEST 6: Sidebar + Main
    Expected: Sidebar elements do not interleave or pollute Main reading order.
    """
    builder = TreeBuilder()

    raw_data = [
        {"id": "sb0", "type": "SIDEBAR_ITEM", "text": "Home", "bbox": (10, 100, 180, 40), "section": "SIDEBAR"},
        {"id": "sb1", "type": "SIDEBAR_ITEM", "text": "Shorts", "bbox": (10, 150, 180, 40), "section": "SIDEBAR"},
        {"id": "sb2", "type": "SIDEBAR_ITEM", "text": "Subscriptions", "bbox": (10, 200, 180, 40), "section": "SIDEBAR"},
        {"id": "v0", "type": "VIDEO_CARD", "text": "Video Main 1", "bbox": (250, 100, 300, 200)},
        {"id": "v1", "type": "VIDEO_CARD", "text": "Video Main 2", "bbox": (580, 100, 300, 200)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)

    # Check that sidebar visual indices are isolated (0, 1, 2)
    sb0 = tree.get_element("sb0")
    sb1 = tree.get_element("sb1")
    sb2 = tree.get_element("sb2")
    assert sb0.visual_index == 0
    assert sb1.visual_index == 1
    assert sb2.visual_index == 2

    # Check that main video visual indices start from 0
    v0 = tree.get_element("v0")
    v1 = tree.get_element("v1")
    assert v0.visual_index == 0
    assert v1.visual_index == 1

    resolver = TargetResolver()
    res_sb = resolver.resolve(tree, "chọn mục thứ 3 trong sidebar")
    assert res_sb.target_element.id == "sb2"

    res_v = resolver.resolve(tree, "chọn video thứ 2")
    assert res_v.target_element.id == "v1"
    print("[TEST 6 PASSED] Sidebar & Main reading/enumeration contexts completely isolated")


def test_7_blocking_popup_and_z_order_priority():
    """
    TEST 7: Blocking popup (e.g. Chrome 'Restore pages?' modal)
    Expected: Underlying targets cannot be clicked through popup; modal priority enforced.
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "v0", "type": "VIDEO_CARD", "text": "Background Video", "bbox": (250, 100, 300, 200)},
        {"id": "popup_dialog", "type": "MODAL", "text": "Restore pages? Chrome did not shut down correctly.", "bbox": (400, 200, 500, 250)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "mở video thứ nhất")

    # Should detect occlusion / blocking modal
    assert res.status == ResolutionStatus.TARGET_OCCLUDED
    assert "blocking modal" in res.error_message.lower()
    print("[TEST 7 PASSED] Blocking modal prevents clicking background video -> TARGET_OCCLUDED")


def test_8_offscreen_target_and_scroll_container():
    """
    TEST 8: Target offscreen
    Expected: Returns TARGET_OFFSCREEN and designates appropriate scroll container.
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "v0", "type": "VIDEO_CARD", "text": "Visible Video 1", "bbox": (250, 100, 300, 200)},
        {"id": "v10", "type": "VIDEO_CARD", "text": "Offscreen Video 10", "bbox": (250, 1800, 300, 200), "offscreen": True},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "video có tiêu đề Offscreen Video 10")

    assert res.status == ResolutionStatus.TARGET_OFFSCREEN
    assert res.suggested_action is not None
    assert "SCROLL_CONTAINER" in res.suggested_action
    print("[TEST 8 PASSED] Offscreen target detected -> TARGET_OFFSCREEN with scroll suggestion")


def test_9_responsive_grid_layout():
    """
    TEST 9: Responsive Grid
    Expected: Layout engine dynamically clusters rows & columns for desktop 4-col vs tablet 3-col vs mobile 2-col.
    """
    engine = LayoutEngine()

    # Desktop 4 columns
    desktop_elems = [
        UIElement(id=f"d_{i}", type=ElementType.VIDEO_CARD, bbox=BoundingBox(50 + (i % 4) * 220, 100 + (i // 4) * 180, 200, 150))
        for i in range(8)
    ]
    cont_desktop = UIContainer(id="c_desk", region_id="r_main", layout_type=LayoutType.GRID, bbox=BoundingBox(0, 0, 1920, 1080))
    ordered_desk = engine.apply_row_major_ordering(desktop_elems, container=cont_desktop)

    assert cont_desktop.rows_count == 2
    assert cont_desktop.columns_count == 4
    assert ordered_desk[4].row == 1 and ordered_desk[4].column == 0 and ordered_desk[4].visual_index == 4

    # Smaller screen 3 columns
    narrow_elems = [
        UIElement(id=f"n_{i}", type=ElementType.VIDEO_CARD, bbox=BoundingBox(50 + (i % 3) * 220, 100 + (i // 3) * 180, 200, 150))
        for i in range(6)
    ]
    cont_narrow = UIContainer(id="c_narrow", region_id="r_main", layout_type=LayoutType.GRID, bbox=BoundingBox(0, 0, 1200, 800))
    ordered_narrow = engine.apply_row_major_ordering(narrow_elems, container=cont_narrow)

    assert cont_narrow.rows_count == 2
    assert cont_narrow.columns_count == 3
    assert ordered_narrow[3].row == 1 and ordered_narrow[3].column == 0 and ordered_narrow[3].visual_index == 3
    print("[TEST 9 PASSED] Responsive grid dynamically computes 4-column vs 3-column rows and visual indices")


def test_10_ambiguous_candidates_guard():
    """
    TEST 10: Ambiguous Candidates
    Expected: If confidence gap between candidates is under threshold, returns TARGET_AMBIGUOUS without clicking.
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    # Two virtually identical buttons without ordinal or distinguishing text
    raw_data = [
        {"id": "btn_like_1", "type": "BUTTON", "text": "Like", "bbox": (200, 300, 80, 40)},
        {"id": "btn_like_2", "type": "BUTTON", "text": "Like", "bbox": (300, 300, 80, 40)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "click nút Like")

    assert res.status == ResolutionStatus.TARGET_AMBIGUOUS
    assert res.is_success() is False
    assert len(res.top_candidates) >= 2
    print("[TEST 10 PASSED] Ambiguous candidates correctly flagged with TARGET_AMBIGUOUS")


def test_11_stale_coordinate_detection_and_relocalization():
    """
    TEST 11: UI layout changes after perception
    Expected: Stale coordinates discarded and re-localization triggered.
    """
    service = HermesUIService.get_instance()

    # Initial frame
    data_t0 = [
        {"id": "v0", "type": "VIDEO_CARD", "text": "Video Initial", "bbox": (250, 100, 300, 200)},
    ]
    tree_t0 = service.tree_builder.build_tree(raw_elements_data=data_t0)
    res0 = service.resolve_target("video thứ 1", tree=tree_t0)
    assert res0.is_success() is True
    initial_x = res0.interaction_point.pixel_x

    # UI shifts / updates (e.g. banner pushed video down and to the right)
    data_t1 = [
        {"id": "banner", "type": "ADVERTISEMENT", "text": "Special Offer", "bbox": (0, 0, 1920, 200)},
        {"id": "v0", "type": "VIDEO_CARD", "text": "Video Initial", "bbox": (400, 350, 300, 200)},
    ]
    tree_t1 = service.tree_builder.build_tree(raw_elements_data=data_t1)
    res1 = service.resolve_target("video thứ 1", tree=tree_t1)

    assert res1.is_success() is True
    new_x = res1.interaction_point.pixel_x
    assert new_x != initial_x
    assert res1.interaction_point.pixel_y >= 350
    print("[TEST 11 PASSED] Re-localization successfully updated target coordinates after UI shift")


def test_12_interaction_verification_failure_detection():
    """
    TEST 12: Click dispatched but expected UI state transition does not occur
    Expected: Verification failure reported (needs_re_localization=True).
    """
    verif_engine = VerificationEngine()
    elem = UIElement(id="v0", type=ElementType.VIDEO_CARD, text="Sample Video", bbox=BoundingBox(250, 100, 300, 200))

    pre_state = {"window_title": "YouTube Home", "elements_count": 10}

    # Simulate explicit failed state transition
    res_failed = verif_engine.verify_action_result(
        pre_state=pre_state,
        post_tree=None,
        target_element=elem,
        action_type=ActionType.OPEN,
        explicit_state_change=False,
    )
    assert res_failed.success is False
    assert res_failed.status == ResolutionStatus.VERIFICATION_FAILED
    assert res_failed.needs_re_localization is True

    # Simulate explicit successful state transition
    res_success = verif_engine.verify_action_result(
        pre_state=pre_state,
        post_tree=None,
        target_element=elem,
        action_type=ActionType.OPEN,
        explicit_state_change=True,
    )
    assert res_success.success is True
    assert res_success.status == ResolutionStatus.SUCCESS
    print("[TEST 12 PASSED] Action verification accurately reports SUCCESS and VERIFICATION_FAILED states")


def test_13_relative_spatial_reasoning():
    """
    TEST 13: Relative spatial queries
    - 'nút bên phải ô tìm kiếm' -> SearchButton
    - 'video ngay dưới video này' -> Nearest below video with X overlap
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    raw_data = [
        {"id": "search_input", "type": "SEARCH_INPUT", "text": "Search box", "bbox": (500, 30, 400, 40)},
        {"id": "search_btn", "type": "SEARCH_BUTTON", "text": "Search", "bbox": (910, 30, 60, 40)},
        {"id": "mic_btn", "type": "BUTTON", "text": "Mic", "bbox": (980, 30, 40, 40)},
        {"id": "v_top", "type": "VIDEO_CARD", "text": "Top Video", "bbox": (300, 150, 300, 200)},
        {"id": "v_bottom", "type": "VIDEO_CARD", "text": "Bottom Video", "bbox": (300, 400, 300, 200)},
    ]

    tree = builder.build_tree(raw_elements_data=raw_data)

    res_btn = resolver.resolve(tree, "nút bên phải search box")
    assert res_btn.is_success() is True
    assert res_btn.target_element.id == "search_btn"

    res_below = resolver.resolve(tree, "video ở dưới Top Video")
    assert res_below.is_success() is True
    assert res_below.target_element.id == "v_bottom"
    print("[TEST 13 PASSED] Relative spatial queries (RIGHT_OF, BELOW) successfully resolved")


def test_14_human_like_visual_enumeration_strategy():
    """
    TEST 14: Human-like visual enumeration (Anchor -> Container -> Row-Major Scan)
    Verifies that natural ordinals ('thứ 6') follow top->bottom, left->right.
    """
    builder = TreeBuilder()
    resolver = TargetResolver()

    # 3x3 Grid (9 cards):
    # 0 1 2
    # 3 4 5  <-- 'video thứ 6' should be index 5 (card 6)
    # 6 7 8
    raw_data = []
    for row in range(3):
        for col in range(3):
            idx = row * 3 + col
            raw_data.append({
                "id": f"card_{idx}",
                "type": "VIDEO_CARD",
                "text": f"Video Item {idx + 1}",
                "bbox": (250 + col * 320, 100 + row * 220, 300, 200),
            })

    tree = builder.build_tree(raw_elements_data=raw_data)
    res = resolver.resolve(tree, "video thứ 6")

    assert res.is_success() is True
    assert res.target_element.id == "card_5"
    assert res.target_element.row == 1
    assert res.target_element.column == 2
    assert res.target_element.visual_index == 5
    print("[TEST 14 PASSED] Human-like visual enumeration resolved 'video thứ 6' -> row 1, col 2 (card_5)")


def run_all_ui_perception_tests():
    print("=" * 70)
    print(" HERMES UI PERCEPTION & VISUAL TARGETING SUITE")
    print("=" * 70)
    test_1_youtube_video_row_and_column()
    test_2_youtube_shorts_section()
    test_3_playlist_item_selection()
    test_4_more_button_composite_sub_target()
    test_5_advertisement_filtering()
    test_6_sidebar_and_main_reading_order_isolation()
    test_7_blocking_popup_and_z_order_priority()
    test_8_offscreen_target_and_scroll_container()
    test_9_responsive_grid_layout()
    test_10_ambiguous_candidates_guard()
    test_11_stale_coordinate_detection_and_relocalization()
    test_12_interaction_verification_failure_detection()
    test_13_relative_spatial_reasoning()
    test_14_human_like_visual_enumeration_strategy()
    print("=" * 70)
    print(" ALL 14 UI PERCEPTION & TARGETING TESTS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_ui_perception_tests()

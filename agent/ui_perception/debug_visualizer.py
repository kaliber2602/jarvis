"""
Visual Debug Marker & Coordinate Context Subsystem for Hermes UI Perception.
Renders precise bounding box overlays, ordinal badges, thumbnail clickable regions,
and target crosshair markers on pre-click screenshots to verify physical interaction points.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional, Sequence

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None

log = logging.getLogger("hermes_ui.debug_visualizer")


class DebugVisualizer:
    """
    Renders visual debug overlays on window/screen captures for visual audit and verification.
    """

    @classmethod
    def get_default_artifact_dir(cls) -> str:
        """Resolve the standard artifact/logs directory."""
        candidates = [
            r"C:\Users\ADMIN\.gemini\antigravity\brain\eb1a2e49-fdb9-42c1-a92b-30a73f7f8e9c",
            os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain", "eb1a2e49-fdb9-42c1-a92b-30a73f7f8e9c"),
            os.path.join(os.getcwd(), "logs"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        os.makedirs(candidates[-1], exist_ok=True)
        return candidates[-1]

    @classmethod
    def draw_target_markers_and_save(
        cls,
        image: Optional[Any],
        ordered_targets: Sequence[Any],
        selected_target: Any,
        click_screen_point: tuple[int, int],
        window_origin: tuple[int, int] = (0, 0),
        client_origin: tuple[int, int] = (0, 0),
        browser_chrome_height: int = 80,
        dpi_scale: float = 1.0,
        output_filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        Draw bounding boxes of all detected cards with ordinal numbers,
        highlight the selected target's thumbnail region, and draw a prominent
        target crosshair at the exact physical click coordinate.
        """
        if Image is None or ImageDraw is None:
            log.warning("[DEBUG_VISUALIZER] PIL not available for visual marker rendering.")
            return None

        # 1. Prepare base image canvas
        if image is not None and hasattr(image, "copy"):
            try:
                canvas = image.copy().convert("RGB")
            except Exception:
                canvas = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
        else:
            canvas = Image.new("RGB", (1920, 1080), color=(30, 30, 30))

        draw = ImageDraw.Draw(canvas)
        img_w, img_h = canvas.size

        # Simple font or default
        font = None
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        # Offset between client origin and screenshot canvas origin
        offset_x = client_origin[0] - window_origin[0]
        offset_y = client_origin[1] - window_origin[1] + browser_chrome_height

        # 2. Draw all detected component bounding boxes & ordinal labels
        for idx, t in enumerate(ordered_targets, start=1):
            t_ordinal = getattr(t, "ordinal", idx) or idx
            t_id = getattr(t, "component_id", getattr(t, "id", f"comp_{idx}"))
            bbox = getattr(t, "bbox", None)

            if isinstance(bbox, (tuple, list)) and len(bbox) >= 4:
                bx, by, bw, bh = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            elif hasattr(bbox, "x"):
                bx, by, bw, bh = float(bbox.x), float(bbox.y), float(bbox.width), float(bbox.height)
            else:
                continue

            card_left = offset_x + bx
            card_top = offset_y + by
            card_right = card_left + bw
            card_bottom = card_top + bh

            is_selected = (t_ordinal == getattr(selected_target, "ordinal", None)) or (t_id == getattr(selected_target, "component_id", None))

            # Outline color
            box_color = (255, 215, 0) if is_selected else (0, 200, 255)  # Gold if selected, else Cyan
            box_width = 3 if is_selected else 2

            # Draw card boundary
            draw.rectangle([card_left, card_top, card_right, card_bottom], outline=box_color, width=box_width)

            # Draw ordinal pill badge at top-left of card
            badge_text = f"#{t_ordinal} ({t_id})"
            draw.rectangle([card_left, card_top - 18, card_left + len(badge_text) * 7 + 10, card_top], fill=(20, 20, 20))
            draw.rectangle([card_left, card_top - 18, card_left + len(badge_text) * 7 + 10, card_top], outline=box_color, width=1)
            draw.text((card_left + 4, card_top - 16), badge_text, fill=(255, 255, 255), font=font)

            # Highlight thumbnail region for selected target
            if is_selected:
                thumb_h = bh * 0.65
                thumb_rect = [card_left + 2, card_top + 2, card_right - 2, card_top + thumb_h]
                draw.rectangle(thumb_rect, outline=(50, 255, 50), width=2)
                draw.rectangle([card_left + 4, card_top + 4, card_left + 150, card_top + 20], fill=(0, 100, 0))
                draw.text((card_left + 6, card_top + 6), "THUMBNAIL (CLICKABLE)", fill=(200, 255, 200), font=font)

        # 3. Draw Crosshairs & Marker at the EXACT Click Screen Coordinate
        sc_x, sc_y = click_screen_point
        click_img_x = sc_x - window_origin[0]
        click_img_y = sc_y - window_origin[1]

        # Clamp to canvas
        cx = max(10, min(img_w - 10, click_img_x))
        cy = max(10, min(img_h - 10, click_img_y))

        # Outer crosshair circle
        draw.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], outline=(255, 0, 100), width=3)
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=(255, 255, 0), width=2)

        # Cross lines
        draw.line([cx - 24, cy, cx + 24, cy], fill=(255, 0, 100), width=3)
        draw.line([cx, cy - 24, cx, cy + 24], fill=(255, 0, 100), width=3)
        draw.line([cx - 18, cy, cx + 18, cy], fill=(255, 255, 255), width=1)
        draw.line([cx, cy - 18, cx, cy + 18], fill=(255, 255, 255), width=1)

        # Center dot
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 255, 255), outline=(0, 0, 0))

        # Target annotation banner
        sel_ord = getattr(selected_target, "ordinal", "?")
        sel_id = getattr(selected_target, "component_id", getattr(selected_target, "id", "?"))
        target_banner = f"TARGET #{sel_ord} [{sel_id}] CLICK POINT: ({sc_x}, {sc_y})"

        banner_x = min(img_w - 320, max(10, cx + 20))
        banner_y = min(img_h - 40, max(10, cy - 28))
        draw.rectangle([banner_x - 4, banner_y - 2, banner_x + len(target_banner) * 7 + 8, banner_y + 18], fill=(200, 0, 50))
        draw.rectangle([banner_x - 4, banner_y - 2, banner_x + len(target_banner) * 7 + 8, banner_y + 18], outline=(255, 255, 255), width=1)
        draw.text((banner_x, banner_y), target_banner, fill=(255, 255, 255), font=font)

        # 4. Save debug image to disk
        art_dir = cls.get_default_artifact_dir()
        ts = int(time.time() * 1000)
        if not output_filename:
            output_filename = f"debug_target_marker_card_{sel_ord}_{ts}.png"

        save_path = os.path.join(art_dir, output_filename)
        try:
            canvas.save(save_path)
            log.info("[DEBUG_VISUAL_MARKER] Saved visual marker debug image: %s", save_path)
            return save_path
        except Exception as ex:
            log.warning("[DEBUG_VISUAL_MARKER] Failed saving visual marker image to '%s': %s", save_path, ex)
            return None

"""
uia_dom_extractor.py

Windows UIAutomation (Accessibility Tree) DOM Extractor for Jarvis Agent (Tier 2 Fallback).
Extracts rendered YouTube video card components directly from the Chromium Accessibility
Engine using Windows UIAutomation COM interfaces.
Operates 100% independently of CDP (port 9222) and browser extensions.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

log = logging.getLogger("jarvis.uia_dom_extractor")


@dataclass(frozen=True)
class UIAVideoCard:
    """Represents a YouTube video card extracted from Chromium Accessibility Tree."""
    ordinal: int
    title: str
    screen_x: int
    screen_y: int
    bbox: Tuple[int, int, int, int]  # (left, top, right, bottom) in physical screen coordinates
    component_id: str = ""
    is_ad: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UIADOMExtractor:
    """
    Tier 2 Safety Net: Extracts YouTube card elements from the native Windows Accessibility Tree.
    """

    _simulated_cards: Optional[List[dict[str, Any]]] = None

    @classmethod
    def set_simulated_cards(cls, cards: Optional[List[dict[str, Any]]]) -> None:
        """Inject simulated UIA video cards for unit testing."""
        cls._simulated_cards = cards

    @classmethod
    def extract_youtube_cards_from_hwnd(cls, hwnd: int) -> List[UIAVideoCard]:
        """
        Traverse Chromium Accessibility Tree of the given window HWND to extract visible YouTube video cards.
        """
        # 1. Simulation / Test Mode
        if cls._simulated_cards is not None:
            cards = []
            for i, raw in enumerate(cls._simulated_cards):
                ordinal = int(raw.get("ordinal", i + 1))
                title = str(raw.get("title", f"Video #{ordinal}"))
                sx = int(raw.get("screen_x", raw.get("center_x", 0)))
                sy = int(raw.get("screen_y", raw.get("center_y", 0)))
                bbox = tuple(raw.get("bbox", (sx - 100, sy - 50, sx + 100, sy + 50)))
                comp_id = str(raw.get("component_id", f"uia_video_{ordinal}"))
                is_ad = bool(raw.get("is_ad", False))
                cards.append(UIAVideoCard(
                    ordinal=ordinal,
                    title=title,
                    screen_x=sx,
                    screen_y=sy,
                    bbox=bbox,
                    component_id=comp_id,
                    is_ad=is_ad,
                ))
            log.info("[UIA_DOM_EXTRACTOR] Extracted %d simulated cards from HWND %d", len(cards), hwnd)
            return cards

        if not hwnd:
            log.warning("[UIA_DOM_EXTRACTOR] Invalid HWND (0) provided.")
            return []

        # 2. Windows UIAutomation COM Inspection
        try:
            import comtypes
            import comtypes.client

            # Ensure COM is initialized in current worker thread
            try:
                comtypes.CoInitialize()
            except Exception:
                pass

            try:
                UIAutomationCore = comtypes.client.GetModule("UIAutomationCore.dll")
                uia = comtypes.client.CreateObject(
                    UIAutomationCore.CUIAutomation,
                    interface=UIAutomationCore.IUIAutomation,
                )
            except Exception:
                # Fallback to direct CLSID creation
                uia = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eeef594}")

            elem = uia.ElementFromHandle(hwnd)
            if not elem:
                log.warning("[UIA_DOM_EXTRACTOR] ElementFromHandle returned None for HWND %d", hwnd)
                return []

            # TreeScope_Descendants = 4
            condition = uia.CreateTrueCondition()
            all_elements = elem.FindAll(4, condition)
            if not all_elements:
                log.warning("[UIA_DOM_EXTRACTOR] FindAll returned 0 elements for HWND %d", hwnd)
                return []

            cards: List[UIAVideoCard] = []
            ordinal = 1
            length = getattr(all_elements, "Length", 0)

            for i in range(length):
                try:
                    el = all_elements.GetElement(i)
                    name = str(el.CurrentName or "").strip()
                    rect = el.CurrentBoundingRectangle
                    if not rect:
                        continue

                    # Bounding rect coordinates
                    left = int(rect[0]) if isinstance(rect, (list, tuple)) else int(getattr(rect, "left", 0))
                    top = int(rect[1]) if isinstance(rect, (list, tuple)) else int(getattr(rect, "top", 0))
                    right = int(rect[2]) if isinstance(rect, (list, tuple)) else int(getattr(rect, "right", 0))
                    bottom = int(rect[3]) if isinstance(rect, (list, tuple)) else int(getattr(rect, "bottom", 0))

                    w = right - left
                    h = bottom - top

                    # Strict size culling: filter out tiny icons or huge window containers
                    # A YouTube video card is typically 150-800px wide and 80-550px high
                    if w < 100 or h < 50 or w > 850 or h > 600:
                        continue

                    # Filter out browser header/window titles & system UI
                    name_lower = name.lower()
                    if name_lower.endswith("- google chrome") or name_lower in ("youtube", "google chrome", "chrome"):
                        continue

                    # Filter out non-video UI elements (navigation bars, search buttons, menus)
                    skip_keywords = [
                        "search", "navigation", "guide", "menu", "youtube home", "explore",
                        "subscriptions", "google chrome", "address and search", "app bar",
                        "minimize", "maximize", "restore", "close", "reload", "back", "forward"
                    ]
                    if any(k in name_lower for k in skip_keywords):
                        continue

                    # Check control type if available to ignore top-level structural panes
                    try:
                        ctrl_type = getattr(el, "CurrentControlType", 0)
                        # 50032=Window, 50030=Document, 50037=TitleBar, 50010=MenuBar, 50021=ToolBar
                        if ctrl_type in (50032, 50030, 50037, 50010, 50021):
                            continue
                    except Exception:
                        pass

                    # Video cards typically have descriptive titles
                    if len(name) > 8:
                        # Target thumbnail center
                        cx = left + (w // 2)
                        cy = top + int(h * 0.4)
                        is_ad = "ad" in name_lower or "sponsored" in name_lower

                        cards.append(UIAVideoCard(
                            ordinal=ordinal,
                            title=name,
                            screen_x=cx,
                            screen_y=cy,
                            bbox=(left, top, right, bottom),
                            component_id=f"uia_video_{ordinal}",
                            is_ad=is_ad,
                        ))
                        ordinal += 1
                        if ordinal > 20:
                            break
                except Exception as node_err:
                    log.debug("[UIA_DOM_EXTRACTOR] Error inspecting element %d: %s", i, node_err)
                    continue

            log.info("[UIA_DOM_EXTRACTOR] Extracted %d YouTube video cards via UIA from HWND %d", len(cards), hwnd)
            return cards

        except Exception as e:
            log.warning("[UIA_DOM_EXTRACTOR] UIA extraction failed for HWND %d: %s", hwnd, e)
            return []

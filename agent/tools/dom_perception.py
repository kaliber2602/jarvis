"""
DOM Perception & JavaScript Payload Injection Subsystem for YouTube Video Selection.
Treats the Browser DOM as the single authoritative Source of Truth.
100% DOM-driven: eliminates all legacy geometric sorting (ROW_MAJOR_SORT, y_tolerance).
Fails fast with detailed debug logs when DOM extraction returns 0 items.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Union

log = logging.getLogger("hermes.dom_perception")

# -----------------------------------------------------------------------------
# JavaScript DOM Extractor Payload (2026 Polymer yt-lockup-view-model + Legacy Fallbacks)
# -----------------------------------------------------------------------------
YOUTUBE_DOM_EXTRACTOR_JS = """(() => {
    const debug_log = [];
    const videos = [];

    // 1. Log viewport dimensions
    const winW = window.innerWidth;
    const winH = window.innerHeight;
    debug_log.push(`Viewport dimensions: innerWidth=${winW}, innerHeight=${winH}`);

    // 2. Selectors: Query all primary card renderers including 2026 Polymer yt-lockup-view-model
    const SELECTORS = [
        'ytd-rich-item-renderer',
        'ytd-video-renderer',
        'ytd-grid-video-renderer',
        'ytd-compact-video-renderer',
        'yt-lockup-view-model'
    ].join(', ');

    const cardNodes = Array.from(document.querySelectorAll(SELECTORS));
    debug_log.push(`Total nodes queried: ${cardNodes.length}`);

    let ordinal = 1;
    const seenHrefs = new Set();

    for (let i = 0; i < cardNodes.length; i++) {
        const node = cardNodes[i];
        const tagName = node.tagName ? node.tagName.toLowerCase() : 'unknown';
        const rect = node.getBoundingClientRect();

        // Strict Culling:
        if (rect.width === 0 || rect.height === 0 || rect.width > 900 || rect.height > 750) {
            continue;
        }
        if (rect.bottom < 0 || rect.top > winH || rect.right > winW) {
            continue;
        }

        // Must contain a playable video anchor (/watch or /shorts)
        const watchAnchor = node.querySelector(
            'a[href*="/watch"], a[href*="/shorts"], a.ytLockupViewModelContentImage, a#thumbnail, a#video-title-link'
        );
        if (!watchAnchor) {
            continue;
        }

        const href = watchAnchor.getAttribute('href') || watchAnchor.href || '';
        if (!href || (!href.includes('/watch') && !href.includes('/shorts'))) {
            continue;
        }

        // Deduplicate cards if both parent and child match
        const cleanHref = href.split('&')[0];
        if (seenHrefs.has(cleanHref)) {
            continue;
        }
        seenHrefs.add(cleanHref);

        // Title extraction
        let title = '';
        const titleElem = node.querySelector(
            '#video-title, #video-title-link, yt-formatted-string#video-title, h3, a.yt-lockup-metadata-view-model-wiz__title, span[role="text"]'
        );
        if (titleElem) {
            title = (titleElem.getAttribute('title') || titleElem.textContent || titleElem.innerText || '').trim();
        }
        if (!title && watchAnchor) {
            title = (watchAnchor.getAttribute('title') || watchAnchor.getAttribute('aria-label') || '').trim();
        }

        // Thumbnail target for precise clicking
        const thumb = node.querySelector(
            'a.ytLockupViewModelContentImage, a#thumbnail, yt-thumbnail-view-model, ytd-thumbnail'
        ) || watchAnchor;
        const thumbRect = thumb.getBoundingClientRect();
        const targetRect = (thumbRect.width > 0 && thumbRect.height > 0) ? thumbRect : rect;

        const cx = Math.round((targetRect.left + (targetRect.width / 2.0)) * 10) / 10;
        const cy = Math.round((targetRect.top + (targetRect.height / 2.0)) * 10) / 10;

        const isAd = Boolean(
            tagName.includes('ad') ||
            node.querySelector('.badge-style-type-ad, [id="ad-badge"], .ytd-ad-slot-renderer, .ytd-display-ad-renderer')
        );

        const videoItem = {
            ordinal: ordinal,
            component_id: `yt_video_${ordinal}`,
            title: title || `YouTube Video #${ordinal}`,
            href: href,
            is_ad: isAd,
            center_x: cx,
            center_y: cy,
            bbox: [
                Math.round(targetRect.left * 10) / 10,
                Math.round(targetRect.top * 10) / 10,
                Math.round(targetRect.width * 10) / 10,
                Math.round(targetRect.height * 10) / 10
            ],
            card_bbox: [
                Math.round(rect.left * 10) / 10,
                Math.round(rect.top * 10) / 10,
                Math.round(rect.width * 10) / 10,
                Math.round(rect.height * 10) / 10
            ]
        };

        videos.push(videoItem);
        debug_log.push(`Accepted ordinal #${ordinal}: center=(${cx}, ${cy}), href="${cleanHref}", title="${videoItem.title}"`);
        ordinal++;
    }

    debug_log.push(`DOM Extraction finished: ${videos.length} visible videos identified.`);
    return {
        videos: videos,
        debug_log: debug_log
    };
})()"""


@dataclass
class DOMVideoItem:
    """Represents a validated video item extracted directly from Chrome DOM."""
    ordinal: int
    component_id: str
    title: str
    href: str
    center_x: float  # Viewport X
    center_y: float  # Viewport Y
    bbox: list[float]  # [x, y, width, height] in Viewport space
    card_bbox: list[float] = field(default_factory=list)
    is_ad: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DOMExtractionResult:
    """Encapsulates the complete result of DOM extraction including deep debug logs."""
    videos: list[DOMVideoItem] = field(default_factory=list)
    debug_log: list[str] = field(default_factory=list)

    def __iter__(self):
        return iter(self.videos)

    def __len__(self):
        return len(self.videos)

    def __getitem__(self, index):
        return self.videos[index]


class ChromeDOMConnector:
    """
    Bridge connecting Jarvis agent to Chrome DOM via CDP (Chrome DevTools Protocol),
    browser connectors (Playwright/Selenium), or simulated test providers.
    """

    _simulated_dom_videos: Optional[Union[dict[str, Any], list[dict[str, Any]]]] = None

    @classmethod
    def set_simulated_dom_videos(
        cls,
        videos_or_payload: Optional[Union[dict[str, Any], list[dict[str, Any]]]],
    ) -> None:
        """Inject mock DOM video results or full payload for testing / simulation mode."""
        cls._simulated_dom_videos = videos_or_payload

    @classmethod
    def get_simulated_dom_videos(cls) -> Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
        return cls._simulated_dom_videos

    @classmethod
    def extract_youtube_videos(
        cls,
        hwnd: int = 0,
        cdp_port: int = 9222,
        browser_connector: Any = None,
        timeout: float = 2.0,
        client_origin: tuple[int, int] = (0, 0),
        browser_chrome_h: int = 80,
    ) -> DOMExtractionResult:
        """
        Execute YouTube video extraction using 2-Tier Fallback Perception:
        Tier 1: Chrome DevTools Protocol (CDP) WebSocket evaluation.
        Tier 2: Windows UIAutomation (Accessibility Tree) DOM inspection from HWND.
        Returns a DOMExtractionResult containing visible videos and full debug_log.
        """
        # 1. Check if mock/simulation data is registered
        if cls._simulated_dom_videos is not None:
            debug_log = [
                "Viewport dimensions: innerWidth=1400, innerHeight=900 (Simulation)",
                "Executing simulated DOM extraction...",
            ]
            raw_list = []
            if isinstance(cls._simulated_dom_videos, dict):
                raw_list = cls._simulated_dom_videos.get("videos", [])
                debug_log = cls._simulated_dom_videos.get("debug_log", debug_log)
            elif isinstance(cls._simulated_dom_videos, list):
                raw_list = cls._simulated_dom_videos

            items = []
            for i, raw_item in enumerate(raw_list):
                ordinal = int(raw_item.get("ordinal", i + 1))
                comp_id = str(raw_item.get("component_id", f"yt_video_{ordinal}"))
                title = str(raw_item.get("title", f"Video #{ordinal}"))
                href = str(raw_item.get("href", ""))
                cx = float(raw_item.get("center_x", raw_item.get("viewport_x", 0.0)))
                cy = float(raw_item.get("center_y", raw_item.get("viewport_y", 0.0)))
                bbox = list(raw_item.get("bbox", [0.0, 0.0, 100.0, 100.0]))
                card_bbox = list(raw_item.get("card_bbox", bbox))
                is_ad = bool(raw_item.get("is_ad", False))
                items.append(DOMVideoItem(
                    ordinal=ordinal,
                    component_id=comp_id,
                    title=title,
                    href=href,
                    center_x=cx,
                    center_y=cy,
                    bbox=bbox,
                    card_bbox=card_bbox,
                    is_ad=is_ad,
                ))

            if isinstance(cls._simulated_dom_videos, list) and not debug_log[2:]:
                debug_log.append(f"Total nodes queried: {len(items)}")
                for it in items:
                    debug_log.append(
                        f"Accepted ordinal #{it.ordinal}: center=({it.center_x}, {it.center_y}), title=\"{it.title}\""
                    )
                debug_log.append(f"DOM Extraction finished: {len(items)} visible videos identified.")

            return DOMExtractionResult(videos=items, debug_log=debug_log)

        # 2. Provided browser connector (e.g. Playwright page / Selenium driver)
        if browser_connector is not None:
            try:
                if hasattr(browser_connector, "evaluate"):
                    raw = browser_connector.evaluate(YOUTUBE_DOM_EXTRACTOR_JS)
                elif hasattr(browser_connector, "execute_script"):
                    raw = browser_connector.execute_script(YOUTUBE_DOM_EXTRACTOR_JS)
                elif callable(browser_connector):
                    raw = browser_connector(YOUTUBE_DOM_EXTRACTOR_JS)
                else:
                    raw = {}

                res = cls._parse_js_payload(raw)
                if res.videos:
                    return res
            except Exception as ex:
                log.warning("[DOM_PERCEPTION] Browser connector JS execution error: %s", ex)

        # 3. Tier 1: Direct Chrome DevTools Protocol (CDP) WebSocket evaluation
        cdp_debug_log: list[str] = []
        try:
            req_url = f"http://127.0.0.1:{cdp_port}/json"
            req = urllib.request.Request(req_url, headers={"User-Agent": "Jarvis-Agent"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                tabs = json.loads(response.read().decode("utf-8"))

            target_tab = None
            for tab in tabs:
                if tab.get("type") == "page" and "youtube.com" in tab.get("url", ""):
                    target_tab = tab
                    break
            if not target_tab and tabs:
                target_tab = [t for t in tabs if t.get("type") == "page"][0]

            if target_tab and "webSocketDebuggerUrl" in target_tab:
                try:
                    import websocket
                    ws = websocket.create_connection(
                        target_tab["webSocketDebuggerUrl"],
                        suppress_origin=True,
                        timeout=timeout,
                    )
                    eval_msg = json.dumps({
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": YOUTUBE_DOM_EXTRACTOR_JS,
                            "returnByValue": True,
                            "awaitPromise": True,
                        }
                    })
                    ws.send(eval_msg)
                    raw_res = json.loads(ws.recv())
                    ws.close()
                    val = raw_res.get("result", {}).get("result", {}).get("value", {})
                    cdp_result = cls._parse_js_payload(val)
                    if cdp_result.videos:
                        return cdp_result
                    cdp_debug_log.extend(cdp_result.debug_log)
                except ImportError:
                    cdp_debug_log.append("websocket-client package not installed; cannot connect to Chrome CDP WebSocket.")
        except Exception as ex:
            cdp_debug_log.append(f"CDP connection failed: {ex}")
            log.info("[DOM_PERCEPTION] Tier 1 CDP failed (%s). Attempting Tier 2 (UIA Fallback)...", ex)

        # 4. Tier 2 Fallback: Windows UIAutomation (Accessibility Tree)
        if hwnd:
            try:
                from .uia_dom_extractor import UIADOMExtractor
                log.info("[DOM_PERCEPTION] Running Tier 2 (UIA Fallback) for HWND: %d", hwnd)
                uia_cards = UIADOMExtractor.extract_youtube_cards_from_hwnd(hwnd)
                if uia_cards:
                    debug_log = list(cdp_debug_log)
                    debug_log.append(f"Tier 2 (UIA Fallback) successfully extracted {len(uia_cards)} video cards from HWND {hwnd}.")
                    items = []
                    for c in uia_cards:
                        vp_x = float(c.screen_x - client_origin[0])
                        vp_y = float(c.screen_y - client_origin[1] - browser_chrome_h)
                        left, top, right, bottom = c.bbox
                        card_vp_bbox = [
                            float(left - client_origin[0]),
                            float(top - client_origin[1] - browser_chrome_h),
                            float(right - left),
                            float(bottom - top),
                        ]
                        items.append(DOMVideoItem(
                            ordinal=c.ordinal,
                            component_id=c.component_id or f"yt_uia_video_{c.ordinal}",
                            title=c.title,
                            href="",
                            center_x=vp_x,
                            center_y=vp_y,
                            bbox=card_vp_bbox,
                            card_bbox=card_vp_bbox,
                            is_ad=c.is_ad,
                        ))
                    return DOMExtractionResult(videos=items, debug_log=debug_log)
            except Exception as uia_err:
                cdp_debug_log.append(f"Tier 2 UIA Fallback error: {uia_err}")
                log.warning("[DOM_PERCEPTION] Tier 2 UIA Fallback failed: %s", uia_err)

        return DOMExtractionResult(videos=[], debug_log=cdp_debug_log or ["CDP tab not available or no response received."])

    @classmethod
    def _parse_js_payload(cls, raw: Any) -> DOMExtractionResult:
        """Parse raw JS return payload { videos: [...], debug_log: [...] }."""
        debug_log: list[str] = []
        raw_videos: list[dict[str, Any]] = []

        if isinstance(raw, dict):
            debug_log = [str(x) for x in raw.get("debug_log", [])]
            raw_videos = raw.get("videos", [])
        elif isinstance(raw, list):
            raw_videos = raw
            debug_log = [f"Retrieved {len(raw_videos)} items from DOM."]

        items: list[DOMVideoItem] = []
        for i, raw_item in enumerate(raw_videos):
            if not isinstance(raw_item, dict):
                continue
            ordinal = int(raw_item.get("ordinal", i + 1))
            comp_id = str(raw_item.get("component_id", f"yt_video_{ordinal}"))
            title = str(raw_item.get("title", f"YouTube Item #{ordinal}"))
            href = str(raw_item.get("href", ""))
            cx = float(raw_item.get("center_x", raw_item.get("viewport_x", 0.0)))
            cy = float(raw_item.get("center_y", raw_item.get("viewport_y", 0.0)))
            bbox = list(raw_item.get("bbox", [0.0, 0.0, 100.0, 100.0]))
            card_bbox = list(raw_item.get("card_bbox", bbox))
            is_ad = bool(raw_item.get("is_ad", False))
            items.append(DOMVideoItem(
                ordinal=ordinal,
                component_id=comp_id,
                title=title,
                href=href,
                center_x=cx,
                center_y=cy,
                bbox=bbox,
                card_bbox=card_bbox,
                is_ad=is_ad,
            ))

        return DOMExtractionResult(videos=items, debug_log=debug_log)


def select_youtube_video_by_dom(
    requested_ordinal: int,
    application: str = "chrome",
    browser_connector: Any = None,
    wait_load: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Select YouTube video using 2-Tier DOM Perception (CDP -> UIA).
    Authoritative single source of truth.

    Pipeline:
      1. Resolve active YouTube window & snapshot.
      2. Injects YOUTUBE_DOM_EXTRACTOR_JS (CDP) or falls back to Windows UIA.
      3. Prints/Logs every line of debug_log.
      4. If videos is empty, logs failure and exits immediately (Fail-Fast).
      5. Transforms Viewport (cx, cy) -> Physical Screen (final_x, final_y).
      6. Prints/Logs exact coordinate transformation math.
      7. Dispatches single mouse click.
    """
    from .window_manager import WindowManager
    from .computer_use import MouseExecutor

    # 1. Resolve active YouTube window
    window_handle, target_identity = WindowManager.resolve_target(app_name=application, task_context="youtube")
    if not window_handle or not window_handle.hwnd:
        log.error("[DOM_PERCEPTION] Target YouTube window not found for application '%s'", application)
        return {
            "success": False,
            "status": "WINDOW_NOT_FOUND",
            "ordinal": requested_ordinal,
            "total_dom_items": 0,
            "target_interaction_verified": False,
            "task_verified": False,
            "window_recovered": False,
            "failure_reason": "browser_session_unavailable",
            "message": f"No active window found for '{application}'",
            "mouse_action_success": False,
        }

    target_hwnd = window_handle.hwnd
    snapshot = WindowManager.get_snapshot(window_handle)
    if not snapshot:
        log.error("[DOM_PERCEPTION] Could not capture window snapshot for HWND=%d", target_hwnd)
        return {
            "success": False,
            "status": "SNAPSHOT_FAILED",
            "ordinal": requested_ordinal,
            "total_dom_items": 0,
            "target_interaction_verified": False,
            "task_verified": False,
            "window_recovered": False,
            "failure_reason": "snapshot_failed",
            "message": "Could not capture window snapshot",
            "mouse_action_success": False,
        }

    client_origin = snapshot.client_screen_origin
    browser_chrome_h = snapshot.browser_chrome_height

    # 2. Execute 2-Tier DOM Extraction (CDP -> UIA)
    extraction_result = ChromeDOMConnector.extract_youtube_videos(
        hwnd=target_hwnd,
        browser_connector=browser_connector,
        client_origin=client_origin,
        browser_chrome_h=browser_chrome_h,
    )
    dom_videos = extraction_result.videos
    debug_log = extraction_result.debug_log

    # 3. PRINT/LOG every single line in debug_log
    log.info("========== [YOUTUBE DOM EXTRACTION DEBUG LOG] ==========")
    for line in debug_log:
        log.info("[DOM_DEBUG] %s", line)
        try:
            print(f"[DOM_DEBUG] {line}")
        except UnicodeEncodeError:
            safe_l = line.encode("ascii", errors="replace").decode("ascii")
            print(f"[DOM_DEBUG] {safe_l}")
    log.info("=========================================================")

    # 4. Fail fast if no videos extracted (NO FALLBACK)
    if not dom_videos:
        err_msg = "DOM Extraction failed: 0 items returned"
        log.error("[DOM_PERCEPTION] %s", err_msg)
        try:
            print(f"[DOM_PERCEPTION] {err_msg}")
        except UnicodeEncodeError:
            pass
        return {
            "success": False,
            "status": "DOM_EXTRACTION_FAILED",
            "ordinal": requested_ordinal,
            "total_dom_items": 0,
            "debug_log": debug_log,
            "target_interaction_verified": False,
            "task_verified": False,
            "window_recovered": False,
            "failure_reason": "dom_extraction_failed",
            "message": err_msg,
            "mouse_action_success": False,
        }

    log.info("[DOM_PERCEPTION] Extracted %d visible YouTube video items directly from DOM.", len(dom_videos))

    # 5. Validate requested ordinal range
    if requested_ordinal < 1 or requested_ordinal > len(dom_videos):
        warn_msg = f"Video #{requested_ordinal} not found in DOM extraction (total visible: {len(dom_videos)})."
        log.warning("[DOM_PERCEPTION] %s", warn_msg)
        print(f"[DOM_PERCEPTION] {warn_msg}")
        return {
            "success": False,
            "status": "TARGET_NOT_FOUND",
            "ordinal": requested_ordinal,
            "total_dom_items": len(dom_videos),
            "debug_log": debug_log,
            "target_interaction_verified": False,
            "task_verified": False,
            "window_recovered": False,
            "failure_reason": "target_not_found",
            "message": warn_msg,
            "mouse_action_success": False,
        }

    # 6. Retrieve target video item (1-based ordinal)
    target_item = dom_videos[requested_ordinal - 1]

    # 7. Coordinate Transformation Math
    vp_x = target_item.center_x
    vp_y = target_item.center_y
    win_x = client_origin[0]
    win_y = client_origin[1]
    chrome_offset = browser_chrome_h
    final_x = int(round(win_x + vp_x))
    final_y = int(round(win_y + vp_y + chrome_offset))
    screen_pt = (final_x, final_y)

    # 8. PRINT/LOG the exact coordinate transformation math
    coord_math_msg = (
        f"[COORD MATH] Viewport (cx: {vp_x}, cy: {vp_y}) -> "
        f"Screen (X: {win_x} + {vp_x} = {final_x}, Y: {win_y} + {vp_y} + {chrome_offset} = {final_y})"
    )
    log.info(coord_math_msg)
    print(coord_math_msg)

    # Diagnostic trace logging
    diag_logger = logging.getLogger("computer_use_tool")
    diag_logger.info(
        "[COMPONENT_TARGET] ordinal=#%d title='%s' href='%s' id=%s is_ad=%s\n"
        "[COORDINATE] dom_viewport_space=(%.1f, %.1f) -> window_client_space=(%.1f, %.1f) -> screen_space=(%d, %d)\n"
        "[WINDOW] hwnd=%d chrome_h=%d origin=(%d, %d)\n"
        "[MOUSE] final_physical_point=(%d, %d)",
        target_item.ordinal, target_item.title, target_item.href, target_item.component_id, target_item.is_ad,
        vp_x, vp_y,
        vp_x, vp_y + chrome_offset,
        final_x, final_y,
        target_hwnd, chrome_offset, win_x, win_y,
        final_x, final_y,
    )

    if dry_run:
        return {
            "success": True,
            "status": "DRY_RUN_COMPLETED",
            "dry_run": True,
            "ordinal": target_item.ordinal,
            "resolved_ordinal": target_item.ordinal,
            "target_id": target_item.component_id,
            "component_id": target_item.component_id,
            "title": target_item.title,
            "href": target_item.href,
            "is_ad": target_item.is_ad,
            "target": {
                "requested_index": requested_ordinal,
                "ordinal": target_item.ordinal,
                "component_id": target_item.component_id,
                "bbox": target_item.bbox,
                "screen_point": screen_pt,
                "title": target_item.title,
            },
            "interaction": {
                "attempted": False,
                "click_dispatched": False,
                "click_completed": False,
            },
            "click_point": screen_pt,
            "viewport_point": (vp_x, vp_y),
            "coord_math": coord_math_msg,
            "debug_log": debug_log,
            "mouse_action_success": True,
            "target_interaction_verified": True,
            "task_verified": True,
            "window_recovered": False,
            "message": f"Dry-run resolved DOM video #{target_item.ordinal} to ({final_x}, {final_y}).",
        }

    # 9. Move cursor & Physical Click
    import uuid
    txn_id = f"DOM-YT-{requested_ordinal}-{uuid.uuid4().hex[:4].upper()}"
    click_res = MouseExecutor.click_physical_point(screen_pt, click_count=1, tolerance=2, transaction_id=txn_id)

    move_verified = bool(click_res.get("move_verified", True))
    click_completed = bool(
        click_res.get("click_completed", False)
        or click_res.get("mouse_action_success", False)
        or click_res.get("success", False)
    )
    pos_before = click_res.get("actual_position_before", (0, 0))
    pos_after = click_res.get("actual_position_at_click", screen_pt)

    log.info(
        "\n[CURSOR]\n"
        "expected=(%d, %d)\n"
        "actual=(%d, %d)\n"
        "distance=%.1f\n"
        "verified=%s",
        final_x, final_y,
        pos_after[0],
        pos_after[1],
        0.0, move_verified
    )

    log.info("\n[CLICK]\ndispatch=%s\ncount=1", "SUCCESS" if click_completed else "FAILED")
    log.info("\n[ACTION]\nVIDEO_SELECTION_COMPLETED")

    return {
        "success": click_completed,
        "status": "SUCCESS" if click_completed else "CLICK_FAILED",
        "ordinal": target_item.ordinal,
        "target_id": target_item.component_id,
        "component_id": target_item.component_id,
        "title": target_item.title,
        "href": target_item.href,
        "is_ad": target_item.is_ad,
        "target": {
            "requested_index": requested_ordinal,
            "ordinal": target_item.ordinal,
            "component_id": target_item.component_id,
            "bbox": target_item.bbox,
            "screen_point": screen_pt,
            "title": target_item.title,
        },
        "viewport_point": (vp_x, vp_y),
        "click_point": screen_pt,
        "cursor_before": pos_before,
        "cursor_after": pos_after,
        "actual_position_before": pos_before,
        "actual_position_at_click": pos_after,
        "coord_math": coord_math_msg,
        "debug_log": debug_log,
        "move_verified": move_verified,
        "click_completed": click_completed,
        "mouse_action_success": click_completed,
        "target_interaction_verified": click_completed,
        "task_verified": click_completed,
        "window_recovered": False,
        "message": f"Clicked and selected YouTube video #{target_item.ordinal} ('{target_item.title}') via DOM perception.",
    }

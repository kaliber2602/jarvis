"""
Browser Controller: High-Level Web Browser Management & Automation Layer.
Coordinates ProcessManager, WindowManager, and Browser Automation (DOM / CDP / Accessibility).
Enforces the fundamental architectural invariant: NAVIGATION NEVER AUTOMATICALLY GENERATES CLICKS.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .process_manager import ProcessManager
from .window_manager import WindowInfo, WindowManager, WindowState
from ..safety_policy import SafetyPolicy

log = logging.getLogger("hermes.browser_controller")


@dataclass
class BrowserTabInfo:
    """Represents a browser tab or page."""
    tab_id: str
    title: str = ""
    url: str = ""
    is_active: bool = True
    dom_accessible: bool = False


@dataclass
class BrowserInstance:
    """Represents an active web browser session."""
    browser_type: str = "chrome"
    main_window_hwnd: int = 0
    process_id: int = 0
    current_url: str = ""
    last_navigated_at: float = 0.0
    active_tab: Optional[BrowserTabInfo] = None
    tabs: list[BrowserTabInfo] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        if not self.main_window_hwnd:
            return False
        w = WindowManager.get_window(self.main_window_hwnd)
        return w is not None and w.is_visible


class BrowserController:
    """
    Authoritative controller for web browser lifecycle, tab management, and navigation.
    Positioned strictly above ProcessManager and WindowManager.
    """

    _active_instance: Optional[BrowserInstance] = None

    @classmethod
    def get_chrome_executable(cls) -> Optional[str]:
        """Locate Google Chrome executable on the current system."""
        if sys.platform == "win32":
            for base in (
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                os.environ.get("LOCALAPPDATA", ""),
            ):
                if not base:
                    continue
                p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
                if os.path.isfile(p):
                    return p
        return shutil.which("google-chrome") or shutil.which("chrome")

    @classmethod
    def get_active_browser_window(cls) -> Optional[WindowInfo]:
        """
        Locate the active or highest-priority browser window using WindowManager.
        Prioritizes top-level Chrome_WidgetWin_1 windows.
        """
        # 1. Check current foreground window
        fg = WindowManager.get_foreground_window()
        if fg and any(b in fg.process_name for b in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe")):
            return fg

        # 2. Check tracked active instance
        if cls._active_instance and cls._active_instance.main_window_hwnd:
            w = WindowManager.get_window(cls._active_instance.main_window_hwnd)
            if w and w.is_interactive:
                return w

        # 3. Enumerate top-level browser windows
        candidates = WindowManager.find_windows(app_name="chrome", include_minimized=True)
        if not candidates:
            candidates = WindowManager.find_windows(app_name="browser", include_minimized=True)

        if not candidates:
            return None

        # Prefer non-minimized, visible, Chrome_WidgetWin_1
        valid_candidates = [c for c in candidates if c.class_name == "Chrome_WidgetWin_1" or "chrome" in c.process_name]
        if not valid_candidates:
            valid_candidates = candidates

        valid_candidates.sort(
            key=lambda c: (
                100 if c.is_foreground else 0,
                50 if not c.is_minimized else 0,
                30 if "youtube" in c.title.lower() else 0,
                c.width * c.height,
            ),
            reverse=True,
        )

        return valid_candidates[0]

    @classmethod
    def navigate(cls, url: str, new_window: bool = False) -> dict[str, Any]:
        """
        Pure Browser Navigation Action (NAVIGATION).
        Opens or navigates to a URL. NEVER generates or triggers a follow-up click.
        """
        allowed, reason = SafetyPolicy.evaluate_action("open_url", {"url": url})
        if not allowed:
            return {"success": False, "error": reason}

        u = url.strip()
        if not u.startswith("http://") and not u.startswith("https://"):
            u = "https://" + u

        log.info("[BROWSER_CONTROLLER] Executing NAVIGATION to URL: %s (new_window=%s)", u, new_window)

        JARVIS_CHROME_PROFILE = os.path.join(os.environ.get("LOCALAPPDATA", "C:\\"), "Jarvis", "ChromeProfile")
        CDP_PORT = 9222

        try:
            chrome_exe = cls.get_chrome_executable()
            if chrome_exe and sys.platform == "win32":
                os.makedirs(JARVIS_CHROME_PROFILE, exist_ok=True)
                args = [
                    chrome_exe,
                    f"--remote-debugging-port={CDP_PORT}",
                    "--remote-allow-origins=*",
                    f"--user-data-dir={JARVIS_CHROME_PROFILE}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
                if new_window:
                    args.append("--new-window")
                args.append(u)
                subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif chrome_exe:
                args = [
                    chrome_exe,
                    f"--remote-debugging-port={CDP_PORT}",
                    "--remote-allow-origins=*",
                ]
                if new_window:
                    args.append("--new-window")
                args.append(u)
                subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform == "win32" and not new_window:
                os.startfile(u)
            else:
                webbrowser.open(u)

            # Update tracked instance
            time.sleep(0.3)
            win = cls.get_active_browser_window()
            hwnd = win.hwnd if win else 0
            pid = win.process_id if win else 0

            cls._active_instance = BrowserInstance(
                browser_type="chrome",
                main_window_hwnd=hwnd,
                process_id=pid,
                current_url=u,
                last_navigated_at=time.time(),
                active_tab=BrowserTabInfo(tab_id="tab_active", title=win.title if win else "", url=u),
            )

            log.info(
                "[BROWSER_CONTROLLER] Navigation completed -> HWND=%d PID=%d url=%s",
                hwnd, pid, u
            )
            return {
                "success": True,
                "action": "NAVIGATE",
                "url": u,
                "hwnd": hwnd,
                "pid": pid,
                "message": f"Navigated to {u}",
            }
        except Exception as ex:
            log.error("[BROWSER_CONTROLLER] Error during navigation to '%s': %s", u, ex)
            return {
                "success": False,
                "action": "NAVIGATE",
                "url": u,
                "error": str(ex),
            }

    @classmethod
    def wait_until_ready(cls, timeout: float = 3.0, interval: float = 0.1) -> bool:
        """
        Wait for browser window to become active, visible, and settled.
        """
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            win = cls.get_active_browser_window()
            if win and win.is_interactive and not win.is_minimized:
                return True
            time.sleep(interval)
        return False

    @classmethod
    def get_current_url(cls) -> str:
        """Get the last known authoritative URL of the active browser session."""
        if cls._active_instance:
            return cls._active_instance.current_url
        return ""

    @classmethod
    def get_page_state(cls) -> dict[str, Any]:
        """Query high-level page readiness and window attributes."""
        win = cls.get_active_browser_window()
        return {
            "is_browser_open": win is not None,
            "hwnd": win.hwnd if win else 0,
            "title": win.title if win else "",
            "is_visible": win.is_visible if win else False,
            "is_minimized": win.is_minimized if win else False,
            "current_url": cls.get_current_url(),
        }

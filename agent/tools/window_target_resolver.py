"""
WindowTargetResolver: Deterministic Desktop Window Target Resolver for Jarvis Computer Use.
Delegates cleanly to WindowManager while providing full backward-compatible interfaces for tests.
Enforces read-only validation and strictly zero hide/show/restore recovery hacks.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import Enum
import logging
import os
import sys
import time
from typing import Any, Optional

from .browser_context import WindowHandle, WindowSnapshot
from .window_manager import WindowInfo, WindowManager

log = logging.getLogger("window_target_resolver")

if sys.platform == "win32":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    dwmapi = getattr(ctypes.windll, "dwmapi", None)
else:
    user32 = None
    dwmapi = None


class TargetResolutionSource(str, Enum):
    COMMAND_SNAPSHOT = "COMMAND_SNAPSHOT"
    LOCKED_TASK_HWND = "LOCKED_TASK_HWND"
    EXPLICIT_APPLICATION = "EXPLICIT_APPLICATION"
    EXPLICIT_HWND = "EXPLICIT_HWND"
    LAST_USER_ACTIVE = "LAST_USER_ACTIVE"
    CURRENT_FOREGROUND = "CURRENT_FOREGROUND"
    RECENT_HISTORY = "RECENT_HISTORY"
    SPATIAL_INDEX = "SPATIAL_INDEX"
    Z_ORDER = "Z_ORDER"
    LARGEST_VISIBLE = "LARGEST_VISIBLE"
    NONE = "NONE"


class BrowserSessionState(str, Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    INVALIDATED = "INVALIDATED"
    RECOVERED = "RECOVERED"


@dataclass
class BrowserSession:
    process_name: str = "chrome.exe"
    pid: int = 0
    hwnd: int = 0
    title: str = ""
    created_at: float = 0.0
    last_validated_at: float = 0.0
    state: str = BrowserSessionState.ACTIVE.value
    session_id: str = ""
    previous_hwnd: int = 0
    window_class: str = ""
    last_known_url: str = ""
    last_foreground_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.last_validated_at:
            self.last_validated_at = self.created_at
        if not self.session_id:
            import uuid
            self.session_id = uuid.uuid4().hex[:8]
        if not self.last_foreground_at:
            self.last_foreground_at = self.created_at

    def is_valid(self) -> bool:
        return self.state in (BrowserSessionState.ACTIVE.value, BrowserSessionState.RECOVERED.value) and self.hwnd > 0

    def rebind(self, new_hwnd: int, new_pid: int = 0, new_title: str = "", new_class: str = ""):
        self.previous_hwnd = self.hwnd
        self.hwnd = new_hwnd
        if new_pid:
            self.pid = new_pid
        if new_title:
            self.title = new_title
        if new_class:
            self.window_class = new_class
        self.last_validated_at = time.time()
        self.state = BrowserSessionState.RECOVERED.value


@dataclass
class TargetContext:
    hwnd: int
    process_name: str = ""
    window_title: str = ""
    pid: int = 0
    locked: bool = True
    created_at: float = 0.0
    last_validated_at: float = 0.0
    state: str = "ACTIVE"
    task_id: str = ""


@dataclass
class WindowTargetSnapshot:
    hwnd: int
    title: str
    pid: int
    proc_name: str
    bounds: tuple[int, int, int, int]
    width: int
    height: int
    area: int
    captured_at: float
    is_valid: bool


class WindowTargetResolver:
    """
    Backward-compatible Target Resolver interface delegating to WindowManager.
    """

    _locked_target: TargetContext | None = None
    _browser_session: BrowserSession | None = None
    _last_user_active_window: WindowTargetSnapshot | None = None
    _window_history: list[WindowTargetSnapshot] = []
    _last_snapshot: WindowTargetSnapshot | None = None

    @classmethod
    def get_protected_pids(cls) -> set[int]:
        return WindowManager.get_protected_pids()

    @classmethod
    def is_jarvis_window(cls, hwnd: int) -> bool:
        return WindowManager.is_jarvis_window(hwnd)

    @classmethod
    def is_cloaked(cls, hwnd: int) -> bool:
        w = WindowManager.get_window(hwnd)
        return w.is_cloaked if w else False

    @classmethod
    def get_window_meta(cls, hwnd: int) -> tuple[str, int, str, tuple[int, int, int, int], int, int] | None:
        w = WindowManager.get_window(hwnd)
        if not w:
            return None
        return (w.title, w.process_id, w.process_name, w.bounds, w.width, w.height)

    @classmethod
    def find_valid_user_windows(cls, include_minimized: bool = False) -> list[tuple[int, str, int, str, int, int]]:
        handles = WindowManager.enumerate_windows(include_minimized=include_minimized)
        res = []
        for h in handles:
            w = WindowManager.get_window(h.hwnd)
            if w:
                res.append((w.hwnd, w.title, w.process_id, w.process_name, w.width, w.height))
        return res

    @classmethod
    def find_spatially_ordered_user_windows(cls, include_minimized: bool = False) -> list[tuple[int, str, int, str, int, int]]:
        wins = cls.find_valid_user_windows(include_minimized=include_minimized)
        def sort_key(w):
            meta = cls.get_window_meta(w[0])
            if not meta:
                return (0, 0)
            bounds = meta[3]
            return (bounds[1] // 100, bounds[0])
        wins.sort(key=sort_key)
        return wins

    @classmethod
    def is_target_locked(cls) -> bool:
        return cls._locked_target is not None and cls._locked_target.locked

    @classmethod
    def resolve_target(
        cls,
        app_name: str | None = None,
        command_name: str = "general",
        index: int | None = None,
        explicit_hwnd: int | None = None,
    ) -> tuple[int, str, str, TargetResolutionSource]:
        # 1. Locked Target
        if cls._locked_target:
            val_ok, _ = cls.validate_target_context(cls._locked_target)
            if val_ok:
                return cls._locked_target.hwnd, cls._locked_target.window_title, cls._locked_target.process_name, TargetResolutionSource.LOCKED_TASK_HWND
            cls._locked_target = None

        # 2. Explicit HWND
        if explicit_hwnd:
            if cls.is_valid_interactive_target(explicit_hwnd):
                meta = cls.get_window_meta(explicit_hwnd)
                return explicit_hwnd, meta[0] if meta else "", meta[2] if meta else "", TargetResolutionSource.EXPLICIT_HWND

        # 3. Spatial Index
        if index is not None:
            ordered = cls.find_spatially_ordered_user_windows(include_minimized=False)
            if 1 <= index <= len(ordered):
                target = ordered[index - 1]
                return target[0], target[1], target[3], TargetResolutionSource.SPATIAL_INDEX

        target_app = (app_name or "").strip().lower()
        is_generic = target_app in WindowManager.GENERIC_WINDOW_ALIASES

        # 4. Explicit Application
        if target_app and not is_generic:
            fg = user32.GetForegroundWindow() if (sys.platform == "win32" and user32) else 0
            aliases = WindowManager.APP_ALIASES.get(target_app, (target_app,))
            if fg and not cls.is_jarvis_window(fg) and cls.is_valid_interactive_target(fg):
                meta = cls.get_window_meta(fg)
                if meta and any(a in meta[2].lower() or a in meta[0].lower() for a in aliases):
                    return fg, meta[0], meta[2], TargetResolutionSource.EXPLICIT_APPLICATION

            valid_wins = cls.find_valid_user_windows(include_minimized=False)
            for w in valid_wins:
                if any(a in w[3].lower() or a in w[1].lower() for a in aliases):
                    return w[0], w[1], w[3], TargetResolutionSource.EXPLICIT_APPLICATION
            return 0, "", "", TargetResolutionSource.NONE

        # 5. Generic Window resolution
        fg = user32.GetForegroundWindow() if (sys.platform == "win32" and user32) else 0
        if fg and not cls.is_jarvis_window(fg) and cls.is_valid_interactive_target(fg):
            meta = cls.get_window_meta(fg)
            return fg, meta[0] if meta else "", meta[2] if meta else "", TargetResolutionSource.CURRENT_FOREGROUND

        if cls._last_snapshot and cls.is_valid_interactive_target(cls._last_snapshot.hwnd):
            return cls._last_snapshot.hwnd, cls._last_snapshot.title, cls._last_snapshot.proc_name, TargetResolutionSource.COMMAND_SNAPSHOT

        if cls._last_user_active_window and cls.is_valid_interactive_target(cls._last_user_active_window.hwnd):
            return cls._last_user_active_window.hwnd, cls._last_user_active_window.title, cls._last_user_active_window.proc_name, TargetResolutionSource.LAST_USER_ACTIVE

        valid_wins = cls.find_valid_user_windows(include_minimized=False)
        if valid_wins:
            w = valid_wins[0]
            return w[0], w[1], w[3], TargetResolutionSource.Z_ORDER

        return 0, "", "", TargetResolutionSource.NONE

    @classmethod
    def is_valid_interactive_target(cls, hwnd: int, check_minimized: bool = True) -> bool:
        if not hwnd:
            return False
        if sys.platform == "win32" and user32:
            if not user32.IsWindow(hwnd):
                return False
            if not user32.IsWindowVisible(hwnd) or cls.is_cloaked(hwnd):
                return False
            if check_minimized and user32.IsIconic(hwnd):
                return False
            rect = getattr(WindowManager, "RECT", None)
            if rect:
                r = rect()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                if (r.right - r.left) < 30 or (r.bottom - r.top) < 30:
                    return False
            return True
    @classmethod
    def validate_target_context(cls, ctx: TargetContext | None = None, check_minimized: bool = True) -> tuple[bool, str]:
        target = ctx or cls._locked_target
        if not target or not target.hwnd:
            return False, "NO_TARGET_CONTEXT"
        if not cls.is_valid_interactive_target(target.hwnd, check_minimized=check_minimized):
            return False, "TARGET_NOT_INTERACTIVE"
        return True, "VALID"

    @classmethod
    def validate_browser_session(
        cls,
        session: BrowserSession | None,
        check_minimized: bool = True,
    ) -> tuple[bool, str]:
        if session is None or not session.hwnd:
            return False, "NO_BROWSER_SESSION"

        if sys.platform == "win32" and user32:
            if not user32.IsWindow(session.hwnd):
                session.state = BrowserSessionState.STALE.value
                return False, "WINDOW_DESTROYED"

            if not user32.IsWindowVisible(session.hwnd) or cls.is_cloaked(session.hwnd):
                session.state = BrowserSessionState.STALE.value
                return False, "WINDOW_NOT_VISIBLE"

            if check_minimized and user32.IsIconic(session.hwnd):
                session.state = BrowserSessionState.STALE.value
                return False, "WINDOW_MINIMIZED"

            if session.pid:
                pid_val = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(session.hwnd, ctypes.byref(pid_val))
                if pid_val.value != 0 and pid_val.value != session.pid:
                    session.state = BrowserSessionState.STALE.value
                    return False, "PID_MISMATCH"

        return True, "VALID"

    @classmethod
    def get_or_create_browser_session(cls, task_context: str = "youtube") -> BrowserSession | None:
        if cls._browser_session and cls._browser_session.is_valid():
            return cls._browser_session

        handle, _ = WindowManager.resolve_target(app_name="chrome", task_context=task_context)
        if not handle:
            return None
        session = cls._browser_session or BrowserSession()
        session.hwnd = handle.hwnd
        session.pid = handle.pid
        session.title = handle.title
        session.process_name = handle.process_name
        session.state = BrowserSessionState.ACTIVE.value
        session.last_validated_at = time.time()
        cls._browser_session = session
        return session

    @classmethod
    def recover_browser_window(
        cls,
        task_context: str = "youtube",
        old_hwnd: int | None = None,
        old_pid: int | None = None,
    ) -> BrowserSession | None:
        """
        Pure read-only discovery of available Chrome windows without hide/show/restore mutations.
        """
        log.info("[WINDOW_TARGET] Resolving candidate Chrome window...")
        try:
            chrome_wins = cls.enumerate_chrome_windows()
            if chrome_wins:
                best_cand = None
                for c in chrome_wins:
                    if task_context and task_context.lower() in c.get("title", "").lower():
                        best_cand = c
                        break
                if not best_cand:
                    best_cand = chrome_wins[0]
                session = cls._browser_session or BrowserSession()
                session.rebind(new_hwnd=best_cand["hwnd"], new_pid=best_cand.get("pid", 0), new_title=best_cand.get("title", ""))
                cls._browser_session = session
                return session
        except Exception:
            pass

        valid_wins = cls.find_valid_user_windows(include_minimized=False)
        for w in valid_wins:
            if "chrome" in w[3].lower() or "chrome" in w[1].lower() or "youtube" in w[1].lower():
                session = cls._browser_session or BrowserSession()
                session.rebind(new_hwnd=w[0], new_pid=w[2], new_title=w[1])
                cls._browser_session = session
                return session

        handle, _ = WindowManager.resolve_target(app_name="chrome", task_context=task_context)
        if not handle:
            return None

        session = cls._browser_session or BrowserSession()
        session.rebind(new_hwnd=handle.hwnd, new_pid=handle.pid, new_title=handle.title)
        cls._browser_session = session
        return session

    @classmethod
    def lock_target(cls, hwnd: int, title: str, proc_name: str, pid: int = 0, task_id: str = "") -> TargetContext:
        cls._locked_target = TargetContext(
            hwnd=hwnd,
            window_title=title,
            process_name=proc_name,
            pid=pid,
            task_id=task_id,
        )
        return cls._locked_target

    @classmethod
    def get_locked_target(cls) -> TargetContext | None:
        return cls._locked_target

    @classmethod
    def release_target(cls) -> None:
        cls._locked_target = None

    @classmethod
    def set_browser_session(cls, session: BrowserSession | None) -> None:
        cls._browser_session = session

    @classmethod
    def get_browser_session(cls) -> BrowserSession | None:
        return cls._browser_session

    @classmethod
    def invalidate_target(cls, hwnd: int) -> None:
        if cls._locked_target and cls._locked_target.hwnd == hwnd:
            cls._locked_target = None
        if cls._browser_session and cls._browser_session.hwnd == hwnd:
            cls._browser_session.state = BrowserSessionState.INVALIDATED.value

    @classmethod
    def record_active_window(cls, hwnd: int) -> WindowTargetSnapshot | None:
        if cls.is_jarvis_window(hwnd):
            return cls._last_user_active_window
        title, pid, proc_name, bounds, w, h = cls.get_window_meta(hwnd)
        snap = WindowTargetSnapshot(
            hwnd=hwnd,
            title=title,
            pid=pid,
            proc_name=proc_name,
            bounds=bounds,
            width=w,
            height=h,
            area=w * h,
            captured_at=time.time(),
            is_valid=True,
        )
        cls._last_user_active_window = snap
        return snap

    @classmethod
    def normalize_to_top_level(cls, hwnd: int) -> int:
        if not hwnd or sys.platform != "win32" or not user32:
            return hwnd
        try:
            # GA_ROOT = 2
            root = user32.GetAncestor(hwnd, 2)
            return root if root else hwnd
        except Exception:
            return hwnd

    @classmethod
    def focus_window(cls, hwnd: int) -> bool:
        info = WindowManager.get_window(hwnd)
        return WindowManager.activate_window(info.to_handle()) if info else False

    @classmethod
    def enumerate_chrome_windows(cls, task_context: str = "", expected_pid: int | None = None) -> list[dict[str, Any]]:
        handles = WindowManager.find_application("chrome", include_minimized=True)
        res = []
        for h in handles:
            w = WindowManager.get_window(h.hwnd)
            if w:
                res.append({
                    "hwnd": w.hwnd,
                    "pid": w.process_id,
                    "proc_name": w.process_name,
                    "title": w.title,
                    "class_name": w.class_name,
                    "is_visible": w.is_visible,
                    "is_iconic": w.is_minimized,
                    "is_zoomed": w.is_maximized,
                    "is_foreground": w.is_foreground,
                    "rect": w.bounds,
                    "area": w.width * w.height,
                    "score": 100,
                })
        return res

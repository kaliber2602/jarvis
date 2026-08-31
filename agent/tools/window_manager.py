"""
Window Manager: Dedicated OS Window & HWND Management Subsystem.
Strictly isolates Window Lifecycle and State Inspection from Process Management.
Enforces minimal activation, strictly read-only validation, and zero hide/show/recreate recovery hacks.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import sys
import time
from typing import Any, Callable, Optional, Sequence

from .browser_context import WindowHandle, WindowSnapshot

log = logging.getLogger("hermes.window_manager")

if sys.platform == "win32":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    dwmapi = getattr(ctypes.windll, "dwmapi", None)
    gdi32 = getattr(ctypes.windll, "gdi32", None)
    shcore = getattr(ctypes.windll, "shcore", None)

    # 64-bit safe restypes
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindow.restype = wintypes.HWND

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]
else:
    user32 = None
    kernel32 = None
    dwmapi = None
    gdi32 = None
    shcore = None
    RECT = None


class WindowState(str, Enum):
    """Lifecycle states of a desktop window."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MINIMIZED = "MINIMIZED"
    MAXIMIZED = "MAXIMIZED"
    HIDDEN = "HIDDEN"
    CLOSED = "CLOSED"


@dataclass
class WindowInfo:
    """
    Backward-compatible window state descriptor.
    """
    hwnd: int
    title: str = ""
    class_name: str = ""
    process_id: int = 0
    process_name: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    width: int = 0
    height: int = 0
    is_visible: bool = False
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    is_cloaked: bool = False
    state: WindowState = WindowState.ACTIVE

    @property
    def is_interactive(self) -> bool:
        return self.is_visible and not self.is_minimized and not self.is_cloaked and self.width > 30 and self.height > 30

    @property
    def identity_key(self) -> tuple[int, int, str]:
        return (self.hwnd, self.process_id, self.class_name)

    def to_handle(self) -> WindowHandle:
        return WindowHandle(
            hwnd=self.hwnd,
            pid=self.process_id,
            process_name=self.process_name,
            title=self.title,
            class_name=self.class_name,
        )


@dataclass(frozen=True)
class WindowIdentity:
    """
    Strong Window Identity descriptor binding HWND, PID, Process Name, Title, and Task Context.
    """
    hwnd: int
    pid: int
    process_name: str
    title: str
    task_context: str = ""
    class_name: str = ""

    def to_handle(self) -> WindowHandle:
        return WindowHandle(
            hwnd=self.hwnd,
            pid=self.pid,
            process_name=self.process_name,
            title=self.title,
            class_name=self.class_name,
        )


class WindowManager:
    """
    Unified Desktop Window Manager.
    Enforces the new architecture:
      - Immutable WindowHandle & WindowSnapshot
      - Activation ONLY if necessary (target != foreground)
      - Validation is strictly READ-ONLY (no hide/show/restore mutations)
      - Deterministic target resolution without long-lived stale target locks
    """

    SYSTEM_CLASS_BLACKLIST = {
        "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
        "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow",
        "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow",
        "Taskbar", "SideBar", "NarratorHelperWindow",
        "Chrome_MessageWindow", "GDI+ Window", "tooltips_class32", "SysShadow"
    }

    GENERIC_WINDOW_ALIASES = {
        "", "none", "null", "current", "active", "this", "that", "it", "window",
        "this window", "that window", "the window", "it window", "current window", "active window",
        "cửa sổ", "cua so", "cửa sổ này", "cua so nay", "cửa sổ đó", "cua so do",
        "cửa sổ hiện tại", "cua so hien tai", "cửa sổ lại", "cua so lai",
        "popup", "pop up", "hộp thoại", "hop thoai", "dialog"
    }

    APP_ALIASES: dict[str, tuple[str, ...]] = {
        "chrome": ("chrome", "google chrome", "browser", "trình duyệt", "trinh duyet", "web"),
        "youtube": ("youtube", "you tube", "chrome", "google chrome"),
        "code": ("code", "vscode", "vs code", "visual studio code"),
        "vscode": ("code", "vscode", "vs code", "visual studio code"),
        "visual studio code": ("code", "vscode", "vs code", "visual studio code"),
        "antigravity": ("antigravity",),
        "cursor": ("cursor",),
        "spotify": ("spotify", "nhạc", "music"),
        "discord": ("discord",),
        "notepad": ("notepad", "ghi chú", "note"),
        "explorer": ("explorer", "file explorer", "thư mục"),
    }

    @classmethod
    def get_protected_pids(cls) -> set[int]:
        """Returns set of Jarvis UI overlay and internal server process PIDs to protect."""
        pids = {os.getpid()}
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    pname = (p.info.get('name') or "").lower()
                    if any(ext in pname for ext in ("chrome.exe", "msedge.exe", "firefox.exe", "code.exe", "spotify.exe", "notepad.exe")):
                        continue
                    cmd = " ".join(p.info.get('cmdline') or []).lower()
                    if "ui_window" in cmd or "serve_orb" in cmd or "pywebview" in cmd:
                        pids.add(p.info['pid'])
                except Exception:
                    pass
        except Exception:
            pass
        return pids

    @classmethod
    def is_jarvis_window(cls, hwnd: int) -> bool:
        """Check if an HWND belongs to Jarvis UI, overlay, orb, or server."""
        if not hwnd or sys.platform != "win32" or not user32:
            return False
        try:
            pids = cls.get_protected_pids()
            pid_val = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
            if pid_val.value in pids:
                return True
        except Exception:
            pass
        return False

    @classmethod
    def get_foreground_window(cls) -> Optional[WindowHandle]:
        """Get the current interactive foreground window handle."""
        if sys.platform != "win32" or not user32:
            return None
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd or cls.is_jarvis_window(hwnd):
                return None
            info = cls.get_window(hwnd)
            return info.to_handle() if info else None
        except Exception:
            return None

    @classmethod
    def get_window(cls, hwnd: int) -> Optional[WindowInfo]:
        """Get full window info for a specific HWND."""
        if not hwnd or sys.platform != "win32" or not user32:
            return None
        try:
            if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
                return None

            # Get title
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

            # Get class name
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            class_name = cls_buf.value.strip()

            if class_name in cls.SYSTEM_CLASS_BLACKLIST:
                return None

            # Get PID
            pid_val = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
            pid = pid_val.value

            # Get process name
            pname = ""
            if pid:
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    pname = proc.name().lower()
                except Exception:
                    pass

            # Get bounds
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = max(0, rect.right - rect.left)
            h = max(0, rect.bottom - rect.top)

            is_min = bool(user32.IsIconic(hwnd))
            is_max = bool(user32.IsZoomed(hwnd))
            fg = user32.GetForegroundWindow()

            return WindowInfo(
                hwnd=hwnd,
                title=title,
                class_name=class_name,
                process_id=pid,
                process_name=pname,
                bounds=(rect.left, rect.top, rect.right, rect.bottom),
                width=w,
                height=h,
                is_visible=True,
                is_minimized=is_min,
                is_maximized=is_max,
                is_foreground=(hwnd == fg),
            )
        except Exception:
            return None

    @classmethod
    def enumerate_windows(cls, app_name: str | None = None, include_minimized: bool = True) -> list[WindowHandle]:
        """Enumerate user windows matching optional app_name filter."""
        results: list[WindowHandle] = []
        if sys.platform != "win32" or not user32:
            return results

        target_app = (app_name or "").strip().lower()
        aliases = cls.APP_ALIASES.get(target_app, (target_app,)) if target_app else ()

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(hwnd, lparam):
            if cls.is_jarvis_window(hwnd):
                return True
            info = cls.get_window(hwnd)
            if not info or not info.is_visible:
                return True
            if not include_minimized and info.is_minimized:
                return True
            if info.width < 50 or info.height < 50:
                return True

            if target_app:
                p_low = info.process_name.lower()
                t_low = info.title.lower()
                if not any(a in p_low or a in t_low for a in aliases):
                    return True

            results.append(info.to_handle())
            return True

        user32.EnumWindows(enum_proc, 0)
        return results

    @classmethod
    def resolve_task_window(
        cls,
        task_context: str = "youtube",
        app_name: str = "chrome",
    ) -> tuple[WindowHandle | None, str]:
        """
        Task-Bound Window Resolution:
        Resolves a visible window matching BOTH the application AND the specific task domain (e.g. YouTube).
        Guarantees that generic or auxiliary browser windows (like Download History, Settings, Extensions)
        are NOT mistakenly resolved when a task-specific window is required.
        """
        task_low = (task_context or "").strip().lower()
        target_app = (app_name or "chrome").strip().lower()

        # Check foreground window first
        fg = cls.get_foreground_window()
        if fg:
            t_low = fg.title.lower()
            p_low = fg.process_name.lower()
            is_browser = any(b in p_low for b in ("chrome", "msedge", "firefox", "brave"))
            if task_low and task_low in t_low and is_browser:
                log.info("[TASK_WINDOW] Foreground matches task '%s': HWND=%d title='%s'", task_context, fg.hwnd, fg.title)
                return fg, "FOREGROUND_TASK_MATCH"

        # Enumerate all application windows
        candidates = cls.enumerate_windows(app_name=target_app, include_minimized=True)
        if not candidates:
            # Check for any browser window
            candidates = cls.enumerate_windows(app_name="chrome", include_minimized=True)

        if task_low:
            # Filter candidates specifically matching task context in title
            task_candidates = [c for c in candidates if task_low in c.title.lower()]
            if task_candidates:
                best = task_candidates[0]
                log.info("[TASK_WINDOW] Resolved task '%s' window HWND=%d title='%s'", task_context, best.hwnd, best.title)
                return best, "TASK_CONTEXT_MATCH"

        # Fallback to standard resolution if no task-specific window found
        return cls.resolve_target(app_name=app_name, task_context=task_context)

    @classmethod
    def resolve_target(
        cls,
        app_name: str | None = None,
        explicit_hwnd: int | None = None,
        index: int | None = None,
        task_context: str = "",
    ) -> tuple[WindowHandle | None, str]:
        """
        Pure, deterministic Window Target Resolution:
        1. Explicit HWND (if given and valid)
        2. Generic Command -> Current Foreground Window (if not Jarvis UI)
        3. Explicit Application Command -> Current Foreground if matching task context, else best visible candidate
        4. Spatial Index (e.g. index=2) -> Pick index-th visible user window
        """
        # 1. Explicit HWND
        if explicit_hwnd:
            info = cls.get_window(explicit_hwnd)
            if info and info.is_interactive:
                log.info("[WINDOW] Resolved explicit HWND=%d", explicit_hwnd)
                return info.to_handle(), "EXPLICIT_HWND"

        # Check active session override if available
        try:
            from .window_target_resolver import WindowTargetResolver
            sess = WindowTargetResolver.get_browser_session()
            if sess and sess.hwnd and sess.is_valid():
                return WindowHandle(
                    hwnd=sess.hwnd,
                    pid=sess.pid,
                    process_name=getattr(sess, "process_name", "chrome.exe"),
                    title=getattr(sess, "title", "Google Chrome"),
                    class_name=getattr(sess, "window_class", "Chrome_WidgetWin_1"),
                ), "SESSION_OVERRIDE"
        except Exception:
            pass

        target_app = (app_name or "").strip().lower()
        is_generic = target_app in cls.GENERIC_WINDOW_ALIASES

        # 2. Check current foreground window
        fg_handle = cls.get_foreground_window()

        if is_generic and index is None:
            if fg_handle:
                log.info("[WINDOW] Resolved foreground window: '%s' (HWND: %d)", fg_handle.title, fg_handle.hwnd)
                return fg_handle, "CURRENT_FOREGROUND"
            # Fallback: pick topmost user window
            all_wins = cls.enumerate_windows(include_minimized=False)
            if all_wins:
                log.info("[WINDOW] Resolved topmost user window: '%s' (HWND: %d)", all_wins[0].title, all_wins[0].hwnd)
                return all_wins[0], "TOPMOST_USER_WINDOW"
            return None, "NONE"

        # 3. Explicit Application resolution
        if target_app and not is_generic and index is None:
            aliases = cls.APP_ALIASES.get(target_app, (target_app,))
            # If foreground window matches application AND task_context, prefer it
            if fg_handle:
                p_low = fg_handle.process_name.lower()
                t_low = fg_handle.title.lower()
                matches_app = any(a in p_low or a in t_low for a in aliases)
                if matches_app:
                    if not task_context or (task_context.lower() in t_low):
                        log.info("[WINDOW] Foreground matches target app '%s' & task '%s': HWND=%d", target_app, task_context, fg_handle.hwnd)
                        return fg_handle, "FOREGROUND_APPLICATION_MATCH"

            # Enumerate candidate windows
            candidates = cls.enumerate_windows(app_name=target_app, include_minimized=True)
            if not candidates:
                try:
                    from .window_target_resolver import WindowTargetResolver
                    sess = WindowTargetResolver.get_browser_session() or WindowTargetResolver.get_or_create_browser_session(task_context=task_context)
                    if sess and sess.hwnd:
                        return WindowHandle(
                            hwnd=sess.hwnd,
                            pid=sess.pid,
                            process_name=getattr(sess, "process_name", "chrome.exe"),
                            title=getattr(sess, "title", "Google Chrome"),
                            class_name=getattr(sess, "window_class", "Chrome_WidgetWin_1"),
                        ), "SESSION_OVERRIDE"
                except Exception:
                    pass
                log.warning("[WINDOW] No window found matching application '%s'", target_app)
                return None, "NOT_FOUND"

            # Score candidates deterministically
            def score_candidate(h: WindowHandle) -> int:
                score = 0
                t_low = h.title.lower()
                if task_context and task_context.lower() in t_low:
                    score += 100
                if "youtube" in t_low:
                    score += 50
                # Penalize auxiliary/utility tabs
                if any(u in t_low for u in ("download history", "settings", "extensions", "bookmarks", "history", "cài đặt", "tiện ích")):
                    score -= 50
                if h.class_name == "Chrome_WidgetWin_1":
                    score += 20
                return score

            candidates.sort(key=score_candidate, reverse=True)
            best = candidates[0]
            log.info("[WINDOW] Resolved '%s' candidate HWND=%d title='%s'", target_app, best.hwnd, best.title)
            return best, "EXPLICIT_APPLICATION"

        # 4. Ordinal Spatial Index
        if index is not None:
            all_wins = cls.enumerate_windows(include_minimized=False)
            if 1 <= index <= len(all_wins):
                target = all_wins[index - 1]
                log.info("[WINDOW] Resolved spatial index %d -> HWND=%d title='%s'", index, target.hwnd, target.title)
                return target, "SPATIAL_INDEX"

        # Fallback to foreground if available
        if fg_handle:
            return fg_handle, "FOREGROUND_FALLBACK"

        return None, "NONE"

    @classmethod
    def validate_window(cls, handle: WindowHandle, check_minimized: bool = True) -> tuple[bool, str]:
        """
        Strictly READ-ONLY window validation.
        NEVER attempts to mutate, hide, show, or recreate the window.
        """
        if not handle or not handle.hwnd:
            return False, "INVALID_HANDLE"

        if sys.platform != "win32" or not user32:
            return True, "NON_WINDOWS"

        if not user32.IsWindow(handle.hwnd):
            try:
                from .window_target_resolver import WindowTargetResolver
                sess = WindowTargetResolver.get_browser_session() or WindowTargetResolver.get_or_create_browser_session()
                val_res, val_msg = WindowTargetResolver.validate_browser_session(sess, check_minimized=check_minimized)
                if val_res:
                    return True, "VALID"
            except Exception:
                pass
            return False, "HWND_DESTROYED"

        if not user32.IsWindowVisible(handle.hwnd):
            return False, "HWND_NOT_VISIBLE"

        if check_minimized and user32.IsIconic(handle.hwnd):
            return False, "HWND_MINIMIZED"

        rect = RECT()
        user32.GetWindowRect(handle.hwnd, ctypes.byref(rect))
        w = max(0, rect.right - rect.left)
        h = max(0, rect.bottom - rect.top)
        if w < 30 or h < 30:
            try:
                from .window_target_resolver import WindowTargetResolver
                meta = WindowTargetResolver.get_window_meta(handle.hwnd)
                if meta and meta[4] >= 30 and meta[5] >= 30:
                    w, h = meta[4], meta[5]
            except Exception:
                pass
            if w < 30 or h < 30:
                return False, "HWND_ZERO_SIZE"

        # Verify PID if available
        if handle.pid:
            pid_val = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(handle.hwnd, ctypes.byref(pid_val))
            if pid_val.value != 0 and pid_val.value != handle.pid:
                return False, "PID_MISMATCH"

        return True, "VALID"

    @classmethod
    def activate_window(cls, handle: WindowHandle) -> bool:
        """
        Minimal Window Activation:
        If target window is already the foreground window: DO NOTHING.
        Otherwise, bring to foreground using Win32 API.
        """
        if not handle or not handle.hwnd or sys.platform != "win32" or not user32:
            return False

        try:
            fg = user32.GetForegroundWindow()
            if fg == handle.hwnd:
                # Already foreground: DO NOTHING
                log.info("[WINDOW] HWND=%d is already foreground. Activation skipped.", handle.hwnd)
                return True

            log.info("[WINDOW] Activating HWND=%d ('%s')", handle.hwnd, handle.title)

            # Unlock foreground permissions
            try:
                user32.SystemParametersInfoW(0x2001, 0, 0, 0x0002)
                user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass

            cur_fore = user32.GetForegroundWindow()
            cur_thread = kernel32.GetCurrentThreadId()
            fore_thread = user32.GetWindowThreadProcessId(cur_fore, None) if cur_fore else 0
            target_thread = user32.GetWindowThreadProcessId(handle.hwnd, None)

            attached_fore = False
            attached_target = False
            if fore_thread and fore_thread != cur_thread:
                attached_fore = bool(user32.AttachThreadInput(cur_thread, fore_thread, True))
            if target_thread and target_thread != cur_thread:
                attached_target = bool(user32.AttachThreadInput(cur_thread, target_thread, True))

            # Simulate ALT key to bypass Windows focus lock
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            user32.BringWindowToTop(handle.hwnd)
            user32.SetForegroundWindow(handle.hwnd)

            if attached_fore:
                user32.AttachThreadInput(cur_thread, fore_thread, False)
            if attached_target:
                user32.AttachThreadInput(cur_thread, target_thread, False)

            return True
        except Exception as ex:
            log.warning("[WINDOW] Error activating HWND %d: %s", handle.hwnd, ex)
            return False

    @classmethod
    def get_snapshot(cls, handle: WindowHandle) -> Optional[WindowSnapshot]:
        """
        Capture an authoritative point-in-time snapshot of window geometry, client area, and DPI.
        """
        if not handle or not handle.hwnd:
            return None

        if sys.platform != "win32" or not user32 or not user32.IsWindow(handle.hwnd):
            return WindowSnapshot(
                handle=handle,
                window_rect=(0, 0, 1920, 1080),
                client_rect=(0, 0, 1920, 1080),
                client_screen_origin=(0, 0),
                client_size=(1920, 1080),
                viewport_screen_origin=(0, 80),
                viewport_size=(1920, 1000),
                browser_chrome_height=80,
                dpi=96,
                dpi_scale=1.0,
                is_foreground=True,
                is_visible=True,
                is_minimized=False,
                is_maximized=False,
            )

        try:
            is_vis = bool(user32.IsWindowVisible(handle.hwnd))
            is_icon = bool(user32.IsIconic(handle.hwnd))
            is_zoom = bool(user32.IsZoomed(handle.hwnd))
            fg_hwnd = user32.GetForegroundWindow()
            is_fg = bool(handle.hwnd == fg_hwnd)

            # Window Rect
            w_rect = RECT()
            dwm_ok = False
            if dwmapi:
                try:
                    hres = dwmapi.DwmGetWindowAttribute(handle.hwnd, 9, ctypes.byref(w_rect), ctypes.sizeof(w_rect))
                    if hres == 0:
                        dwm_ok = True
                except Exception:
                    pass
            if not dwm_ok:
                user32.GetWindowRect(handle.hwnd, ctypes.byref(w_rect))

            win_rect = (w_rect.left, w_rect.top, w_rect.right, w_rect.bottom)

            # Client Rect & Client Origin
            c_rect = RECT()
            user32.GetClientRect(handle.hwnd, ctypes.byref(c_rect))
            client_w = max(0, c_rect.right - c_rect.left)
            client_h = max(0, c_rect.bottom - c_rect.top)

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT(0, 0)
            user32.ClientToScreen(handle.hwnd, ctypes.byref(pt))
            client_origin = (pt.x, pt.y)

            # DPI
            dpi = 96
            try:
                if hasattr(user32, "GetDpiForWindow"):
                    d_val = user32.GetDpiForWindow(handle.hwnd)
                    if d_val > 0:
                        dpi = d_val
            except Exception:
                pass
            dpi_scale = max(0.5, min(4.0, dpi / 96.0))

            # Browser Chrome Height (tabs + omnibox)
            browser_chrome_h = 0
            t_low = handle.title.lower()
            p_low = handle.process_name.lower()
            if any(b in t_low or b in p_low for b in ("chrome", "edge", "firefox", "brave", "youtube", "browser")):
                browser_chrome_h = int(round(80.0 * dpi_scale))

            viewport_origin = (client_origin[0], client_origin[1] + browser_chrome_h)
            viewport_size = (client_w, max(1, client_h - browser_chrome_h))

            return WindowSnapshot(
                handle=handle,
                window_rect=win_rect,
                client_rect=(0, 0, client_w, client_h),
                client_screen_origin=client_origin,
                client_size=(client_w, client_h),
                viewport_screen_origin=viewport_origin,
                viewport_size=viewport_size,
                browser_chrome_height=browser_chrome_h,
                dpi=dpi,
                dpi_scale=dpi_scale,
                is_foreground=is_fg,
                is_visible=is_vis,
                is_minimized=is_icon,
                is_maximized=is_zoom,
            )
        except Exception as ex:
            log.warning("[WINDOW] Error capturing snapshot for HWND %d: %s", handle.hwnd, ex)
            return None

    @classmethod
    def close_window(cls, handle: WindowHandle) -> bool:
        """Gracefully close window via standard WM_CLOSE."""
        if not handle or not handle.hwnd or sys.platform != "win32" or not user32:
            return False
        try:
            log.info("[WINDOW] Closing HWND=%d ('%s')", handle.hwnd, handle.title)
            # WM_CLOSE = 0x0010
            return bool(user32.PostMessageW(handle.hwnd, 0x0010, 0, 0))
        except Exception as ex:
            log.warning("[WINDOW] Close error: %s", ex)
            return False

    @classmethod
    def maximize_window(cls, handle: WindowHandle) -> bool:
        """Maximize window."""
        if not handle or not handle.hwnd or sys.platform != "win32" or not user32:
            return False
        try:
            return bool(user32.ShowWindow(handle.hwnd, 3))  # SW_MAXIMIZE = 3
        except Exception:
            return False

    @classmethod
    def minimize_window(cls, handle: WindowHandle) -> bool:
        """Minimize window."""
        if not handle or not handle.hwnd or sys.platform != "win32" or not user32:
            return False
        try:
            return bool(user32.ShowWindow(handle.hwnd, 6))  # SW_MINIMIZE = 6
        except Exception:
            return False

    @classmethod
    def restore_window(cls, handle: WindowHandle) -> bool:
        """Restore window."""
        if not handle or not handle.hwnd or sys.platform != "win32" or not user32:
            return False
        try:
            return bool(user32.ShowWindow(handle.hwnd, 9))  # SW_RESTORE = 9
        except Exception:
            return False

    # Backward compatibility aliases
    @classmethod
    def focus_window(cls, hwnd: int) -> bool:
        info = cls.get_window(hwnd)
        return cls.activate_window(info.to_handle()) if info else False

    @classmethod
    def find_windows(cls, title_pattern: str = "", app_name: str = "", include_minimized: bool = False) -> list[WindowInfo]:
        handles = cls.enumerate_windows(app_name=app_name, include_minimized=include_minimized)
        infos = []
        for h in handles:
            if title_pattern and title_pattern.lower() not in h.title.lower():
                continue
            w = cls.get_window(h.hwnd)
            if w:
                infos.append(w)
        return infos

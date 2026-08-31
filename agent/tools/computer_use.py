"""
Windows Computer Use Tool:
Enables Hermes Agent to interact with the Windows Desktop,
launch and focus applications, simulate input, and control windows.
Refactored to use unified WindowManager, CoordinateMapper, and UIInteractionService.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from ..safety_policy import SafetyPolicy
from .browser_context import WindowHandle, WindowSnapshot
from .coordinate_mapper import CoordinateMapper
from .interaction_executor import InteractionExecutor
from .ui_interaction_service import UIInteractionService
from .window_manager import WindowManager

log = logging.getLogger("computer_use_tool")

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None


class MouseExecutor:
    """
    Physical mouse executor facade delegating directly to InteractionExecutor.
    """

    @classmethod
    def set_simulation_mode(cls, enabled: bool = True) -> None:
        InteractionExecutor.set_simulation_mode(enabled)

    @classmethod
    def set_simulated_cursor(cls, x: int, y: int) -> None:
        InteractionExecutor.set_simulated_cursor(x, y)

    @classmethod
    def set_simulated_move_override(cls, override_pos: Optional[tuple[int, int]]) -> None:
        InteractionExecutor.set_simulated_move_override(override_pos)

    @classmethod
    def get_cursor_position(cls, force_fresh: bool = True) -> tuple[int, int]:
        return InteractionExecutor.get_cursor_position()

    @classmethod
    def move(
        cls,
        target_x: int,
        target_y: int,
        duration: Optional[float] = None,
        smooth: bool = True,
        tolerance: int = 2,
    ) -> dict[str, Any]:
        return InteractionExecutor.move((target_x, target_y), duration=duration, smooth=smooth, tolerance=tolerance)

    @classmethod
    def click_physical_point(
        cls,
        point: Any,  # (x, y) or object with x, y
        click_count: int = 1,
        button: str = "left",
        tolerance: int = 2,
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        x = getattr(point, "x", point[0] if isinstance(point, (tuple, list)) else 0)
        y = getattr(point, "y", point[1] if isinstance(point, (tuple, list)) else 0)
        return InteractionExecutor.click((x, y), click_count=click_count, button=button, tolerance=tolerance, transaction_id=transaction_id)

    @classmethod
    def double_click(cls, target_x: int, target_y: int, button: str = "left", transaction_id: Optional[str] = None) -> dict[str, Any]:
        return InteractionExecutor.double_click((target_x, target_y), button=button, transaction_id=transaction_id)

    @classmethod
    def right_click(cls, target_x: int, target_y: int, transaction_id: Optional[str] = None) -> dict[str, Any]:
        return InteractionExecutor.right_click((target_x, target_y), transaction_id=transaction_id)


class ComputerUseTool:
    """
    Windows desktop automation and application control tool.
    """

    KNOWN_APP_PATHS: dict[str, list[str]] = {
        "chrome": [
            r"Google\Chrome\Application\chrome.exe",
        ],
        "google chrome": [
            r"Google\Chrome\Application\chrome.exe",
        ],
        "browser": [
            r"Google\Chrome\Application\chrome.exe",
        ],
        "vscode": [
            r"Programs\Microsoft VS Code\Code.exe",
            r"Microsoft VS Code\Code.exe",
        ],
        "visual studio code": [
            r"Programs\Microsoft VS Code\Code.exe",
            r"Microsoft VS Code\Code.exe",
        ],
        "vs code": [
            r"Programs\Microsoft VS Code\Code.exe",
            r"Microsoft VS Code\Code.exe",
        ],
        "code": [
            r"Programs\Microsoft VS Code\Code.exe",
            r"Microsoft VS Code\Code.exe",
        ],
        "antigravity": [
            r"Programs\antigravity\Antigravity.exe",
            r"Programs\Antigravity\Antigravity.exe",
            r"antigravity\Antigravity.exe",
        ],
        "cursor": [
            r"Programs\cursor\Cursor.exe",
            r"Programs\Cursor\Cursor.exe",
        ],
        "spotify": [
            r"Spotify\Spotify.exe",
        ],
        "discord": [
            r"Discord\Update.exe --processStart Discord.exe",
        ],
        "notepad": [
            r"notepad.exe",
        ],
        "calc": [
            r"calc.exe",
        ],
        "explorer": [
            r"explorer.exe",
        ]
    }

    WEB_SERVICES: dict[str, str] = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "chatgpt": "https://chatgpt.com",
        "openai": "https://chatgpt.com",
        "gemini": "https://gemini.google.com",
        "claude": "https://claude.ai",
        "github": "https://github.com",
        "spotify": "https://open.spotify.com",
        "discord": "https://discord.com/app",
        "notion": "https://www.notion.so",
        "figma": "https://www.figma.com",
        "canva": "https://www.canva.com",
        "reddit": "https://www.reddit.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "netflix": "https://www.netflix.com",
        "gmail": "https://mail.google.com",
        "drive": "https://drive.google.com",
        "maps": "https://maps.google.com",
        "docs": "https://docs.google.com",
        "sheets": "https://sheets.google.com",
        "whatsapp": "https://web.whatsapp.com",
        "telegram": "https://web.telegram.org",
        "messenger": "https://www.messenger.com",
    }

    PURE_WEB_SERVICES: set[str] = {
        "youtube", "google", "chatgpt", "openai", "gemini", "claude", "github",
        "gmail", "drive", "maps", "docs", "sheets", "facebook", "instagram",
        "twitter", "x", "reddit", "netflix"
    }

    @classmethod
    def find_app_executable(cls, name: str) -> str | None:
        """Resolve executable path for a given application name."""
        name = name.strip().lower()
        if sys.platform != "win32":
            return shutil.which(name)

        # 1. Standard PATH lookup
        which_path = shutil.which(name)
        if which_path:
            return which_path

        # 2. Check in AppRegistry
        try:
            from ..app_registry import AppRegistry
            reg = AppRegistry.get_instance()
            app_info = reg.find_app(name) or reg.find_by_exact_alias(name)
            if app_info and app_info.executable:
                if os.path.isabs(app_info.executable) and os.path.isfile(app_info.executable):
                    return app_info.executable
                p = shutil.which(app_info.executable)
                if p:
                    return p
        except Exception:
            pass

        # 3. Check in Program Files and Local AppData
        roots = [
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("APPDATA", ""),
            os.environ.get("SystemRoot", r"C:\Windows"),
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
        ]

        sub_paths = cls.KNOWN_APP_PATHS.get(name, [f"{name}.exe"])
        for root in roots:
            if not root:
                continue
            for sub in sub_paths:
                candidate = os.path.join(root, sub)
                if os.path.isfile(candidate):
                    return candidate

        return None

    @classmethod
    def open_application(cls, app_name: str, args: list[str] | None = None) -> dict[str, Any]:
        """Launch or open a desktop application or web/cloud service."""
        allowed, reason = SafetyPolicy.evaluate_action("open_application", {"app_name": app_name})
        if not allowed:
            return {"success": False, "error": reason}

        from .browser_tool import BrowserTool
        cleaned_name = app_name.strip().lower()

        # Pure web services open directly in browser
        if cleaned_name in cls.PURE_WEB_SERVICES:
            url = cls.WEB_SERVICES.get(cleaned_name, f"https://www.{cleaned_name}.com")
            log.info("[COMPUTER_USE] Opening web service '%s' -> %s", app_name, url)
            return BrowserTool.open_url(url)

        exe = cls.find_app_executable(app_name)
        cmd_list = [exe or app_name]
        if args:
            cmd_list.extend(args)

        popen_kw: dict = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

        try:
            if exe:
                proc = subprocess.Popen(cmd_list, **popen_kw)
                log.info("[COMPUTER_USE] Launched local app '%s' (PID: %d)", app_name, proc.pid)
                time.sleep(0.4)
                cls.switch_window(app_name)
                return {"success": True, "message": f"Launched {app_name} successfully.", "pid": proc.pid}
            else:
                if cleaned_name in cls.WEB_SERVICES:
                    cloud_url = cls.WEB_SERVICES[cleaned_name]
                    log.info("[COMPUTER_USE] Opening web version of '%s': %s", app_name, cloud_url)
                    return BrowserTool.open_url(cloud_url)

                try:
                    os.startfile(app_name)
                    time.sleep(0.4)
                    cls.switch_window(app_name)
                    return {"success": True, "message": f"Started {app_name}."}
                except Exception:
                    import urllib.parse
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(app_name)}"
                    return BrowserTool.open_url(search_url)
        except Exception as e:
            if cleaned_name in cls.WEB_SERVICES:
                return BrowserTool.open_url(cls.WEB_SERVICES[cleaned_name])
            return {"success": False, "error": f"Failed to start {app_name}: {str(e)}"}

    @classmethod
    def get_active_window_context(cls) -> dict[str, Any]:
        """Inspect the active foreground window context."""
        fg = WindowManager.get_foreground_window()
        if not fg:
            return {"app": "unknown", "title": "", "is_browser": False, "is_youtube": False, "is_vscode": False}

        t_low = fg.title.lower()
        p_low = fg.process_name.lower()
        is_youtube = "youtube" in t_low or "youtube" in p_low
        is_browser = is_youtube or any(k in t_low or k in p_low for k in ("chrome", "google", "edge", "firefox", "brave", "opera"))
        is_vscode = any(k in t_low or k in p_low for k in ("visual studio code", "vscode", "code.exe", "code"))

        app = "unknown"
        if is_youtube:
            app = "youtube"
        elif is_browser:
            app = "chrome"
        elif is_vscode:
            app = "vscode"
        elif "antigravity" in t_low or "antigravity" in p_low:
            app = "antigravity"
        elif "spotify" in t_low or "spotify" in p_low:
            app = "spotify"
        elif "notepad" in t_low or "notepad" in p_low:
            app = "notepad"

        return {
            "hwnd": fg.hwnd,
            "title": fg.title,
            "app": app,
            "proc_name": fg.process_name,
            "is_browser": is_browser,
            "is_youtube": is_youtube,
            "is_vscode": is_vscode,
        }

    @classmethod
    def find_user_windows(cls, include_minimized: bool = False) -> list[tuple[int, str, int, str, int, int]]:
        from .window_target_resolver import WindowTargetResolver
        return WindowTargetResolver.find_valid_user_windows(include_minimized=include_minimized)

    @classmethod
    def get_target_or_active_window(cls, app_name: str | None = None) -> tuple[int, str, str]:
        from .window_target_resolver import WindowTargetResolver
        hwnd, title, proc, _ = WindowTargetResolver.resolve_target(app_name=app_name)
        return hwnd, title, proc

    @classmethod
    def _force_focus_hwnd(cls, hwnd: int) -> bool:
        info = WindowManager.get_window(hwnd)
        if info:
            return WindowManager.activate_window(info.to_handle())
        return WindowManager.activate_window(WindowHandle(hwnd=hwnd, pid=0, process_name="", title="", class_name=""))

    @classmethod
    def switch_window(cls, app_name: str = "", index: int | None = None) -> dict[str, Any]:
        """Switch focus to the specified application or ordinal window."""
        target_handle, source = WindowManager.resolve_target(app_name=app_name, index=index)
        if not target_handle:
            return {"success": False, "error": f"Window '{app_name or index or 'target'}' not found."}

        success = WindowManager.activate_window(target_handle)
        if success:
            return {"success": True, "to": target_handle.title, "message": f"Switched to {target_handle.title}."}
        return {"success": False, "error": f"Failed to switch to {target_handle.title}."}

    @classmethod
    def close_window(cls, app_name: str | None = None, hwnd: int | None = None) -> dict[str, Any]:
        """Close the active window or target application window."""
        from .window_target_resolver import WindowTargetResolver
        res_hwnd, title, proc, src = WindowTargetResolver.resolve_target(app_name=app_name, explicit_hwnd=hwnd)
        if not res_hwnd:
            return {"success": False, "error": "No active window found to close."}

        cls._force_focus_hwnd(res_hwnd)
        if sys.platform == "win32" and user32:
            try:
                user32.PostMessageW(res_hwnd, 0x0010, 0, 0)
                user32.PostMessageW(res_hwnd, 0x0112, 0xF060, 0)
                time.sleep(0.05)
                WindowTargetResolver.release_target()
                return {"success": True, "message": f"Closed {title}."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        WindowTargetResolver.release_target()
        return {"success": True, "message": f"Closed {title}."}

    @classmethod
    def minimize_window(cls, app_name: str | None = None) -> dict[str, Any]:
        """Minimize the active window or target application window."""
        from .window_target_resolver import WindowTargetResolver
        res_hwnd, title, proc, src = WindowTargetResolver.resolve_target(app_name=app_name)
        if not res_hwnd:
            return {"success": False, "error": "No active window found to minimize."}

        cls._force_focus_hwnd(res_hwnd)
        if sys.platform == "win32" and user32:
            try:
                user32.ShowWindow(res_hwnd, 6)  # SW_MINIMIZE
                user32.PostMessageW(res_hwnd, 0x0112, 0xF020, 0)  # WM_SYSCOMMAND, SC_MINIMIZE
                return {"success": True, "message": f"Minimized {title}."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "message": f"Minimized {title}."}

    @classmethod
    def maximize_window(cls, app_name: str | None = None) -> dict[str, Any]:
        """Maximize the active window or target application window."""
        from .window_target_resolver import WindowTargetResolver
        res_hwnd, title, proc, src = WindowTargetResolver.resolve_target(app_name=app_name)
        if not res_hwnd:
            return {"success": False, "error": "No active window found to maximize."}

        cls._force_focus_hwnd(res_hwnd)
        if sys.platform == "win32" and user32:
            try:
                user32.ShowWindow(res_hwnd, 3)  # SW_MAXIMIZE
                user32.PostMessageW(res_hwnd, 0x0112, 0xF030, 0)  # WM_SYSCOMMAND, SC_MAXIMIZE
                return {"success": True, "message": f"Maximized {title}."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "message": f"Maximized {title}."}

    @classmethod
    def restore_window(cls, app_name: str | None = None) -> dict[str, Any]:
        """Restore a minimized or maximized window."""
        from .window_target_resolver import WindowTargetResolver
        res_hwnd, title, proc, src = WindowTargetResolver.resolve_target(app_name=app_name)
        if not res_hwnd:
            return {"success": False, "error": "No active window found to restore."}

        cls._force_focus_hwnd(res_hwnd)
        if sys.platform == "win32" and user32:
            try:
                user32.ShowWindow(res_hwnd, 9)  # SW_RESTORE
                user32.PostMessageW(res_hwnd, 0x0112, 0xF120, 0)  # WM_SYSCOMMAND, SC_RESTORE
                return {"success": True, "message": f"Restored {title}."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": True, "message": f"Restored {title}."}

    @classmethod
    def snap_window(cls, position: str = "left", app_name: str | None = None) -> dict[str, Any]:
        """Snap or position window on screen."""
        pos = position.lower().replace("-", "_").replace(" ", "_").strip()
        if pos == "maximize":
            return cls.maximize_window(app_name)
        elif pos == "minimize":
            return cls.minimize_window(app_name)
        elif pos == "restore":
            return cls.restore_window(app_name)

        target_handle, _ = WindowManager.resolve_target(app_name=app_name)
        if not target_handle:
            return {"success": False, "error": "No active window found to snap."}

        WindowManager.activate_window(target_handle)
        if sys.platform != "win32" or not user32:
            return {"success": True, "message": f"Snapped window to {pos}."}

        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

        work_rect = RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work_rect), 0)
        sw = work_rect.right - work_rect.left
        sh = work_rect.bottom - work_rect.top
        sx = work_rect.left
        sy = work_rect.top

        half_w = sw // 2
        half_h = sh // 2

        pos_map = {
            "top_left": (sx, sy, half_w, half_h),
            "top_right": (sx + half_w, sy, half_w, half_h),
            "bottom_left": (sx, sy + half_h, half_w, half_h),
            "bottom_right": (sx + half_w, sy + half_h, half_w, half_h),
            "left": (sx, sy, half_w, sh),
            "right": (sx + half_w, sy, half_w, sh),
            "center": (sx + sw // 6, sy + sh // 8, (sw * 2) // 3, (sh * 3) // 4),
        }

        if pos in pos_map:
            x, y, w, h = pos_map[pos]
            user32.ShowWindow(target_handle.hwnd, 9)  # SW_RESTORE
            user32.SetWindowPos(target_handle.hwnd, 0, x, y, w, h, 0x0040)
            return {"success": True, "message": f"Snapped window to {pos}."}

        return {"success": False, "error": f"Unknown snap position '{position}'"}

    @classmethod
    def manage_tab(cls, action: str = "next", index: int | None = None) -> dict[str, Any]:
        """Manage browser / application tabs."""
        act = action.lower().strip()
        if act in ("next", "next_tab", "tab_tiep_theo", "chuyen_tab"):
            return cls.press_hotkey("ctrl+tab")
        elif act in ("previous", "prev", "previous_tab", "tab_truoc", "quay_lai_tab"):
            return cls.press_hotkey("ctrl+shift+tab")
        elif act in ("new", "new_tab", "mo_tab_moi", "tao_tab"):
            return cls.press_hotkey("ctrl+t")
        elif act in ("close", "close_tab", "dong_tab", "tat_tab"):
            return cls.press_hotkey("ctrl+w")
        elif act in ("reopen", "reopen_tab", "khoi_phuc_tab"):
            return cls.press_hotkey("ctrl+shift+t")
        elif act in ("select", "select_tab", "chon_tab") and index is not None:
            idx = min(9, max(1, index))
            return cls.press_hotkey(f"ctrl+{idx}")

        return {"success": False, "error": f"Unknown tab action '{action}'"}

    @classmethod
    def type_text(cls, text: str) -> dict[str, Any]:
        """Type text into active window."""
        allowed, reason = SafetyPolicy.evaluate_action("type_text", {"text": text})
        if not allowed:
            return {"success": False, "error": reason}

        if sys.platform == "win32":
            try:
                safe_text = text.replace("'", "''").replace('"', '`"').replace("{", "{{").replace("}", "}}")
                ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{safe_text}')"
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5.0,
                )
                return {"success": True, "message": f"Typed '{text}'"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "type_text is only supported on Windows."}

    @classmethod
    def press_hotkey(cls, hotkey: str) -> dict[str, Any]:
        """Simulate keyboard shortcuts."""
        allowed, reason = SafetyPolicy.evaluate_action("press_hotkey", {"hotkey": hotkey})
        if not allowed:
            return {"success": False, "error": reason}

        if sys.platform == "win32":
            key_map = {
                "ctrl+t": "^t", "ctrl+w": "^w", "ctrl+n": "^n", "ctrl+s": "^s",
                "ctrl+f": "^f", "ctrl+c": "^c", "ctrl+v": "^v", "ctrl+a": "^a",
                "ctrl+l": "^l", "ctrl+k": "^k", "ctrl+p": "^p", "ctrl+r": "^r",
                "ctrl+tab": "^{TAB}", "ctrl+shift+tab": "^+{TAB}",
                "ctrl+shift+t": "^+t", "ctrl+shift+f": "^+f",
                "ctrl+1": "^1", "ctrl+2": "^2", "ctrl+3": "^3", "ctrl+4": "^4",
                "ctrl+5": "^5", "ctrl+6": "^6", "ctrl+7": "^7", "ctrl+8": "^8", "ctrl+9": "^9",
                "alt+tab": "%{TAB}", "alt+left": "%{LEFT}", "alt+right": "%{RIGHT}",
                "f5": "{F5}", "enter": "{ENTER}", "escape": "{ESC}", "esc": "{ESC}",
                "tab": "{TAB}", "f11": "{F11}", "space": " ",
            }
            send_str = key_map.get(hotkey.lower(), hotkey)
            try:
                ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{send_str}')"
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5.0,
                )
                return {"success": True, "message": f"Pressed hotkey {hotkey}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "press_hotkey is only supported on Windows."}

    @classmethod
    def paste_and_enter(cls, text: str) -> dict[str, Any]:
        """Copy text to clipboard and paste with Ctrl+V + Enter."""
        allowed, reason = SafetyPolicy.evaluate_action("type_text", {"text": text})
        if not allowed:
            return {"success": False, "error": reason}

        if sys.platform == "win32":
            try:
                escaped = text.replace("'", "''")
                ps_cmd = f"Set-Clipboard -Value '{escaped}'"
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=3.0,
                )
                time.sleep(0.05)
                ps_cmd2 = "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^v{ENTER}')"
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd2],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=3.0,
                )
                return {"success": True, "message": f"Pasted '{text}' and pressed Enter."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "paste_and_enter is only supported on Windows."}

    @classmethod
    def search_in_active_window(cls, query: str) -> dict[str, Any]:
        """Search within active window."""
        ctx = cls.get_active_window_context()
        if ctx.get("is_youtube"):
            cls.click_coordinate(0.48, 0.16)
            time.sleep(0.1)
            cls.press_hotkey("ctrl+a")
            time.sleep(0.05)
            return cls.paste_and_enter(query)
        elif ctx.get("is_browser"):
            cls.press_hotkey("ctrl+l")
            time.sleep(0.1)
            return cls.paste_and_enter(query)
        elif ctx.get("is_vscode"):
            cls.press_hotkey("ctrl+shift+f")
            time.sleep(0.1)
            return cls.paste_and_enter(query)

        from .browser_tool import BrowserTool
        return BrowserTool.search_web(query)

    @classmethod
    def scroll_page(cls, direction: str = "down", amount: int = 6) -> dict[str, Any]:
        """Scroll active window or page."""
        if sys.platform != "win32" or not user32:
            return {"success": True, "message": f"Scrolled {direction}."}

        dir_clean = (direction or "down").strip().lower()
        try:
            if dir_clean in ("top", "đầu trang", "dau trang", "lên đầu", "len dau"):
                user32.keybd_event(0x24, 0, 0, 0)  # VK_HOME
                time.sleep(0.05)
                user32.keybd_event(0x24, 0, 0x0002, 0)
                return {"success": True, "message": "Scrolled to top of page."}
            elif dir_clean in ("bottom", "cuối trang", "cuoi trang", "xuống cuối", "xuong cuoi"):
                user32.keybd_event(0x23, 0, 0, 0)  # VK_END
                time.sleep(0.05)
                user32.keybd_event(0x23, 0, 0x0002, 0)
                return {"success": True, "message": "Scrolled to bottom of page."}

            is_up = dir_clean in ("up", "lên", "len", "trên", "tren", "scroll up")
            delta = 120 if is_up else -120
            notches = max(1, min(20, amount))

            for _ in range(notches):
                user32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(delta).value, 0)
                time.sleep(0.02)

            return {"success": True, "message": f"Scrolled {direction}."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def click_coordinate(cls, x_ratio: float, y_ratio: float, click_count: int = 1) -> dict[str, Any]:
        """Click at relative coordinate within active window."""
        fg = WindowManager.get_foreground_window()
        if fg:
            snap = WindowManager.get_snapshot(fg)
            if snap:
                tx = int(snap.client_screen_origin[0] + snap.client_size[0] * x_ratio)
                ty = int(snap.client_screen_origin[1] + snap.client_size[1] * y_ratio)
                res = InteractionExecutor.click((tx, ty), click_count=click_count)
                return {
                    "success": res.get("click_completed", True),
                    "mouse_action_success": res.get("click_completed", True),
                    "target_interaction_verified": False,
                    "click_point": (tx, ty),
                    "message": f"Clicked at ({tx}, {ty})",
                }

        tx = int(1920 * x_ratio)
        ty = int(1080 * y_ratio)
        res = InteractionExecutor.click((tx, ty), click_count=click_count)
        return {
            "success": res.get("click_completed", True),
            "mouse_action_success": res.get("click_completed", True),
            "target_interaction_verified": False,
            "click_point": (tx, ty),
            "message": f"Clicked at ({tx}, {ty})",
        }

    @classmethod
    def click_entity(cls, entity_name: str, app_name: str = "chrome") -> dict[str, Any]:
        """Click entity shortcut in window."""
        cls.switch_window(app_name)
        time.sleep(0.2)
        ent = entity_name.lower().strip()
        if ent in ("play", "pause", "play_pause"):
            return cls.press_hotkey("k")
        elif ent in ("fullscreen", "toan man hinh"):
            return cls.press_hotkey("f")
        elif ent in ("mute", "unmute", "tat tieng"):
            return cls.press_hotkey("m")

        entity_coords = {
            "video_1": (0.35, 0.45), "video 1": (0.35, 0.45),
            "video_2": (0.72, 0.45), "video 2": (0.72, 0.45),
            "video_3": (0.35, 0.80), "video 3": (0.35, 0.80),
            "video_4": (0.72, 0.80), "video 4": (0.72, 0.80),
            "search_bar": (0.48, 0.16), "search": (0.48, 0.16),
        }
        if ent in entity_coords:
            xr, yr = entity_coords[ent]
            return cls.click_coordinate(xr, yr)
        return {"success": False, "error": f"Unknown entity '{entity_name}'"}

    @classmethod
    def select_youtube_video(
        cls,
        index: int = 1,
        application: str = "chrome",
        wait_load: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Select/play the N-th YouTube video using DOM Perception as the authoritative Source of Truth.
        Extracts exact thumbnail coordinates directly from Chrome DOM, eliminating legacy geometric estimations.
        """
        from .dom_perception import select_youtube_video_by_dom
        return select_youtube_video_by_dom(
            requested_ordinal=index,
            application=application,
            wait_load=wait_load,
            dry_run=dry_run,
        )

    @classmethod
    def select_youtube_video_by_dom(
        cls,
        requested_ordinal: int = 1,
        application: str = "chrome",
        wait_load: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Select/play the N-th YouTube video using DOM Perception as the authoritative Source of Truth.
        Extracts exact thumbnail coordinates directly from Chrome DOM, bypassing static Python math.
        """
        from .dom_perception import select_youtube_video_by_dom
        return select_youtube_video_by_dom(
            requested_ordinal=requested_ordinal,
            application=application,
            wait_load=wait_load,
            dry_run=dry_run,
        )

    @classmethod
    def resolve_and_click_target(
        cls,
        query: str,
        action: str = "open",
        app_name: str = "chrome",
        wait_load: bool = True,
    ) -> dict[str, Any]:
        """
        Perceive active UI window, resolve target object, and click safe interaction point.
        """
        # Parse ordinal from query if applicable
        import re
        m = re.search(r"(?:video|clip)?\s*(?:thứ|thu|số|so|#)?\s*(\d+)", query.lower())
        idx = int(m.group(1)) if m else 1
        if any(k in query.lower() for k in ("video", "clip", "youtube")):
            return cls.select_youtube_video(index=idx, application=app_name, wait_load=wait_load)

        return cls.select_youtube_video(index=idx, application=app_name, wait_load=wait_load)

    @classmethod
    def run_powershell(cls, command: str) -> dict[str, Any]:
        """Execute a safe PowerShell command."""
        allowed, reason = SafetyPolicy.evaluate_action("run_powershell", {"command": command})
        if not allowed:
            return {"success": False, "error": reason}

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                timeout=15.0,
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "returncode": res.returncode,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

"""
Windows Computer Use Tool:
Enables Hermes Agent to interact with the Windows Desktop,
launch and focus applications, simulate input, and control windows.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..safety_policy import SafetyPolicy

log = logging.getLogger("computer_use_tool")

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None


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
        """Launch or open a desktop application or web service."""
        allowed, reason = SafetyPolicy.evaluate_action("open_application", {"app_name": app_name})
        if not allowed:
            return {"success": False, "error": reason}

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
    def open_application(cls, app_name: str, args: list[str] | None = None) -> dict[str, Any]:
        """Launch or open a desktop application or web/cloud service with automatic cloud fallback."""
        allowed, reason = SafetyPolicy.evaluate_action("open_application", {"app_name": app_name})
        if not allowed:
            return {"success": False, "error": reason}

        from .browser_tool import BrowserTool

        cleaned_name = app_name.strip().lower()

        # 1. Pure web services open directly in browser
        if cleaned_name in cls.PURE_WEB_SERVICES:
            url = cls.WEB_SERVICES.get(cleaned_name, f"https://www.{cleaned_name}.com")
            log.info("[COMPUTER_USE] Opening web service '%s' -> %s", app_name, url)
            return BrowserTool.open_url(url)

        # 2. Check for local desktop application
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
                # 3. If app is not installed locally, check for known cloud/web version
                if cleaned_name in cls.WEB_SERVICES:
                    cloud_url = cls.WEB_SERVICES[cleaned_name]
                    log.info("[COMPUTER_USE] Local app '%s' not found. Opening on-cloud web version: %s", app_name, cloud_url)
                    return BrowserTool.open_url(cloud_url)

                # Try startfile fallback
                try:
                    os.startfile(app_name)
                    log.info("[COMPUTER_USE] Started '%s' via os.startfile", app_name)
                    time.sleep(0.4)
                    cls.switch_window(app_name)
                    return {"success": True, "message": f"Started {app_name}."}
                except Exception:
                    # 4. Final cloud fallback: search for tool on web/cloud
                    import urllib.parse
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(app_name)}"
                    log.info("[COMPUTER_USE] App '%s' not found locally. Falling back to web search: %s", app_name, search_url)
                    return BrowserTool.open_url(search_url)
        except Exception as e:
            # If local launch crashes, gracefully fallback to cloud version or web search
            if cleaned_name in cls.WEB_SERVICES:
                return BrowserTool.open_url(cls.WEB_SERVICES[cleaned_name])
            log.warning("[COMPUTER_USE] Failed to launch application '%s': %s", app_name, e)
            return {"success": False, "error": f"Failed to start {app_name}: {str(e)}"}

    @classmethod
    def get_active_window_context(cls) -> dict[str, Any]:
        """
        Inspect the active foreground window and return application and title context.
        """
        if sys.platform != "win32":
            return {"app": "unknown", "title": "", "is_browser": False, "is_youtube": False, "is_vscode": False}

        try:
            import ctypes
            import ctypes.wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"app": "unknown", "title": "", "is_browser": False, "is_youtube": False, "is_vscode": False}

            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

            title_lower = title.lower()
            is_youtube = "youtube" in title_lower
            is_browser = any(k in title_lower for k in ("chrome", "google", "edge", "firefox", "brave", "youtube"))
            is_vscode = any(k in title_lower for k in ("visual studio code", "vscode", ".py", ".js", ".html", ".md", ".json"))

            app = "unknown"
            if is_youtube:
                app = "youtube"
            elif is_browser:
                app = "chrome"
            elif is_vscode:
                app = "vscode"

            return {
                "hwnd": hwnd,
                "title": title,
                "app": app,
                "is_browser": is_browser,
                "is_youtube": is_youtube,
                "is_vscode": is_vscode,
            }
        except Exception as e:
            log.debug("[COMPUTER_USE] Error inspecting window context: %s", e)
            return {"app": "unknown", "title": "", "is_browser": False, "is_youtube": False, "is_vscode": False}

    @classmethod
    def paste_and_enter(cls, text: str) -> dict[str, Any]:
        """
        Copy text to Windows clipboard and paste with Ctrl+V + Enter.
        Guarantees 100% Unicode accuracy for Vietnamese and complex queries.
        """
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
                log.info("[COMPUTER_USE] Pasted text and pressed Enter: '%s'", text[:50])
                return {"success": True, "message": f"Pasted '{text}' and pressed Enter."}
            except Exception as e:
                log.warning("[COMPUTER_USE] Failed to paste and enter: %s", e)
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "paste_and_enter is only supported on Windows."}

    @classmethod
    def search_in_active_window(cls, query: str) -> dict[str, Any]:
        """
        Intelligently search within the active application window without creating duplicate windows.
        - In YouTube: Focuses YouTube search bar entity, pastes query, presses Enter.
        - In Chrome / Browser: Focuses Omnibox (Ctrl+L), pastes query, presses Enter.
        - In VS Code: Focuses Find (Ctrl+Shift+F).
        - Otherwise: Opens browser with search.
        """
        ctx = cls.get_active_window_context()
        log.info("[COMPUTER_USE] Active window context for search: app='%s', title='%s'", ctx.get("app"), ctx.get("title"))

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
    def type_text(cls, text: str) -> dict[str, Any]:
        """Type text into the currently active window using PowerShell / Windows keyboard simulation."""
        allowed, reason = SafetyPolicy.evaluate_action("type_text", {"text": text})
        if not allowed:
            return {"success": False, "error": reason}

        if sys.platform == "win32":
            try:
                # Send text via PowerShell SendKeys
                safe_text = text.replace("'", "''").replace('"', '`"').replace("{", "{{").replace("}", "}}")
                ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{safe_text}')"
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5.0,
                )
                log.info("[COMPUTER_USE] Typed text: '%s'", text[:40])
                return {"success": True, "message": f"Typed '{text}'"}
            except Exception as e:
                log.warning("[COMPUTER_USE] Failed to type text: %s", e)
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "type_text is only supported on Windows."}

    @classmethod
    def press_hotkey(cls, hotkey: str) -> dict[str, Any]:
        """
        Simulate pressing key combinations (e.g. 'ctrl+t', 'ctrl+w', 'enter', 'f11').
        """
        allowed, reason = SafetyPolicy.evaluate_action("press_hotkey", {"hotkey": hotkey})
        if not allowed:
            return {"success": False, "error": reason}

        if sys.platform == "win32":
            # Map friendly names to SendKeys format
            key_map = {
                "ctrl+t": "^t",
                "ctrl+w": "^w",
                "ctrl+n": "^n",
                "ctrl+s": "^s",
                "ctrl+f": "^f",
                "ctrl+c": "^c",
                "ctrl+v": "^v",
                "ctrl+a": "^a",
                "ctrl+l": "^l",
                "ctrl+k": "^k",
                "ctrl+p": "^p",
                "ctrl+r": "^r",
                "ctrl+tab": "^{TAB}",
                "ctrl+shift+tab": "^+{TAB}",
                "ctrl+shift+t": "^+t",
                "ctrl+shift+f": "^+f",
                "ctrl+1": "^1",
                "ctrl+2": "^2",
                "ctrl+3": "^3",
                "ctrl+4": "^4",
                "ctrl+5": "^5",
                "ctrl+6": "^6",
                "ctrl+7": "^7",
                "ctrl+8": "^8",
                "ctrl+9": "^9",
                "alt+tab": "%{TAB}",
                "alt+left": "%{LEFT}",
                "alt+right": "%{RIGHT}",
                "f5": "{F5}",
                "enter": "{ENTER}",
                "escape": "{ESC}",
                "esc": "{ESC}",
                "tab": "{TAB}",
                "f11": "{F11}",
                "space": " ",
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
                log.info("[COMPUTER_USE] Pressed hotkey: %s", hotkey)
                return {"success": True, "message": f"Pressed hotkey {hotkey}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "press_hotkey is only supported on Windows."}

    @classmethod
    def snap_window(cls, position: str = "left") -> dict[str, Any]:
        """
        Snap or move the active window to a specific screen position.
        Positions: 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'left', 'right', 'center', 'maximize', 'minimize', 'restore'.
        """
        if sys.platform != "win32" or not user32:
            return {"success": False, "error": "snap_window only supported on Windows."}

        pos = position.lower().replace("-", "_").replace(" ", "_").strip()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"success": False, "error": "No active window found."}

        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        half_w = sw // 2
        half_h = sh // 2

        pos_map = {
            "top_left": (0, 0, half_w, half_h),
            "top_right": (half_w, 0, half_w, half_h),
            "bottom_left": (0, half_h, half_w, half_h),
            "bottom_right": (half_w, half_h, half_w, half_h),
            "left": (0, 0, half_w, sh),
            "half_left": (0, 0, half_w, sh),
            "right": (half_w, 0, half_w, sh),
            "half_right": (half_w, 0, half_w, sh),
            "center": (sw // 6, sh // 8, (sw * 2) // 3, (sh * 3) // 4),
        }

        if pos == "maximize":
            return cls.maximize_window()
        elif pos == "minimize":
            return cls.minimize_window()
        elif pos == "restore":
            user32.ShowWindow(hwnd, 9)
            return {"success": True, "message": "Restored window."}

        if pos in pos_map:
            x, y, w, h = pos_map[pos]
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE to unmaximize if needed
            time.sleep(0.05)
            user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0040)  # SWP_SHOWWINDOW
            log.info("[COMPUTER_USE] Snapped window to '%s' (%d, %d, %d, %d)", pos, x, y, w, h)
            return {"success": True, "message": f"Snapped window to {pos}."}

        return {"success": False, "error": f"Unknown snap position '{position}'"}

    @classmethod
    def manage_tab(cls, action: str = "next", index: int | None = None) -> dict[str, Any]:
        """
        Manage and navigate tabs inside the active application (Browser, VS Code, etc.).
        Actions: 'next', 'previous', 'select', 'new', 'close', 'reopen'.
        """
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
    def switch_window(cls, app_name: str | None = None) -> dict[str, Any]:
        """
        Switch focus to a specific application window (e.g. 'chrome', 'vscode', 'antigravity')
        or cycle to the next window in Z-order with full awareness of current and target positions.
        """
        if sys.platform != "win32":
            return {"success": False, "error": "switch_window is only supported on Windows."}

    @classmethod
    def _force_focus_hwnd(cls, hwnd: int) -> bool:
        """Force a window HWND to the 1st foreground position on Windows using Win32 API."""
        if not hwnd or sys.platform != "win32":
            return False
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Restore window if minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # 2. SystemParametersInfo unlock & AllowSetForegroundWindow
        try:
            user32.SystemParametersInfoW(0x2001, 0, 0, 0x0002)  # SPI_SETFOREGROUNDLOCKTIMEOUT = 0
            user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass

        # 3. AttachThreadInput to foreground thread and target thread
        cur_fore = user32.GetForegroundWindow()
        cur_thread = kernel32.GetCurrentThreadId()
        fore_thread = user32.GetWindowThreadProcessId(cur_fore, None)
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)

        attached_fore = False
        attached_target = False
        if fore_thread != cur_thread and fore_thread != 0:
            attached_fore = bool(user32.AttachThreadInput(cur_thread, fore_thread, True))
        if target_thread != cur_thread and target_thread != 0:
            attached_target = bool(user32.AttachThreadInput(cur_thread, target_thread, True))

        # 4. Pulse Alt key to bypass Windows focus stealing prevention
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        # 5. BringWindowToTop and SetForegroundWindow
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        # 6. Z-order topmost bump trick to guarantee 1st display position
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_FLAGS = 0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_FLAGS)
        user32.SetForegroundWindow(hwnd)

        if attached_fore:
            user32.AttachThreadInput(cur_thread, fore_thread, False)
        if attached_target:
            user32.AttachThreadInput(cur_thread, target_thread, False)

        return True

    @classmethod
    def _find_target_window_native(cls, target: str) -> tuple[int, str]:
        """Find matching window HWND and Title natively via Win32 in Python."""
        if sys.platform != "win32":
            return 0, ""
        try:
            import win32gui
            import win32process
            import psutil
        except ImportError:
            return 0, ""

        q = target.lower().strip()
        protected_pids = cls._get_protected_pids_csv().split(",")
        protected_set = {int(p.strip()) for p in protected_pids if p.strip().isdigit()}

        system_bad_titles = (
            "windows input experience", "default ime", "msctfime ui", "gdi+ window",
            "program manager", "textinputhost", "systemsettings", "cortana", "searchhost", "taskbar"
        )

        windows: list[tuple[int, str, str]] = []  # hwnd, title, proc_name

        def _enum(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            t = win32gui.GetWindowText(hwnd).strip()
            if not t:
                return True
            t_low = t.lower()
            if any(bad in t_low for bad in system_bad_titles):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in protected_set:
                return True
            pname = ""
            try:
                pname = psutil.Process(pid).name().lower()
            except Exception:
                pass
            windows.append((hwnd, t, pname))
            return True

        try:
            win32gui.EnumWindows(_enum, None)
        except Exception:
            pass

        if not windows:
            return 0, ""

        if not q:
            target_win = windows[1] if len(windows) > 1 else windows[0]
            return target_win[0], target_win[1]

        for hwnd, t, pname in windows:
            t_low = t.lower()
            if (q in t_low or q in pname
                or (q in ("code", "visual studio code", "vscode") and ("code" in pname or "code" in t_low or "vscode" in t_low))
                or (q in ("chrome", "google chrome", "browser") and ("chrome" in pname or "chrome" in t_low or "google" in t_low or "youtube" in t_low))
                or (q == "spotify" and ("spotify" in pname or "spotify" in t_low))
                or (q == "notepad" and ("notepad" in pname or "notepad" in t_low))):
                return hwnd, t

        return 0, ""

    @classmethod
    def switch_window(cls, app_name: str = "") -> dict[str, Any]:
        """
        Switch focus to the specified application window or cycle to the next window.
        """
        if sys.platform != "win32":
            return {"success": False, "error": "switch_window is only supported on Windows."}

        target = (app_name or "").strip().lower()
        if target in ("next", "other", "cửa sổ khác", "cua so khac", "cửa sổ", "cua so", "window", "tab"):
            target = ""
        elif target in ("google chrome", "browser", "trình duyệt", "trinh duyet", "web browser", "web"):
            target = "chrome"
        elif target in ("visual studio code", "vs code", "vscode", "code editor"):
            target = "code"

        # Tier 1: Native Win32 search & focus
        hwnd, title = cls._find_target_window_native(target)
        if hwnd:
            cls._force_focus_hwnd(hwnd)
            try:
                import win32com.client
                wsh = win32com.client.Dispatch("WScript.Shell")
                wsh.AppActivate(title)
            except Exception:
                pass
            log.info("[COMPUTER_USE] Native Win32 switched focus to '%s' (HWND: %s)", title, hwnd)
            return {"success": True, "to": title, "message": f"Switched to {title}."}

        # Tier 2: PowerShell WSwitch fallback
        protected_csv = cls._get_protected_pids_csv()
        ps_cmd = (
            f"$excludePids = @({protected_csv}); "
            f"$targetQuery = '{target}'; "
            "Add-Type -TypeDefinition '"
            "using System; using System.Collections.Generic; using System.Text; using System.Diagnostics; using System.Runtime.InteropServices; "
            "public class WSwitch { "
            "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); "
            "  [DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr h, StringBuilder t, int c); "
            "  [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p); "
            "  [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p); "
            "  [DllImport(\"user32.dll\")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lp); "
            "  [DllImport(\"user32.dll\")] public static extern bool IsWindowVisible(IntPtr h); "
            "  [DllImport(\"user32.dll\")] public static extern bool IsIconic(IntPtr h); "
            "  [DllImport(\"user32.dll\")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach); "
            "  [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr h); "
            "  [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr h, int c); "
            "  [DllImport(\"user32.dll\")] public static extern bool BringWindowToTop(IntPtr h); "
            "  [DllImport(\"user32.dll\")] public static extern void SwitchToThisWindow(IntPtr h, bool fUnknown); "
            "  [DllImport(\"user32.dll\")] public static extern bool SetWindowPos(IntPtr h, IntPtr hInsert, int x, int y, int cx, int cy, uint f); "
            "  [DllImport(\"user32.dll\")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo); "
            "  [DllImport(\"user32.dll\")] public static extern bool SystemParametersInfo(uint uiAction, uint uiParam, IntPtr pvParam, uint fWinIni); "
            "  [DllImport(\"user32.dll\")] public static extern bool AllowSetForegroundWindow(int dwProcessId); "
            "  [DllImport(\"kernel32.dll\")] public static extern uint GetCurrentThreadId(); "
            "  static readonly IntPtr HWND_TOPMOST = new IntPtr(-1); "
            "  static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2); "
            "  public delegate bool EnumWindowsProc(IntPtr h, IntPtr lp); "
            "  public class WInfo { public IntPtr Hwnd; public string Title; public uint Pid; public string ProcName; } "
            "  public static void ForceFocus(IntPtr targetHwnd) { "
            "    if (targetHwnd == IntPtr.Zero) return; "
            "    IntPtr curFore = GetForegroundWindow(); "
            "    uint curThread = GetCurrentThreadId(); "
            "    uint foreThread = 0; GetWindowThreadProcessId(curFore, out foreThread); "
            "    uint targetThread = 0; GetWindowThreadProcessId(targetHwnd, out targetThread); "
            "    try { SystemParametersInfo(0x2001, 0, IntPtr.Zero, 0x0002); AllowSetForegroundWindow(-1); } catch {} "
            "    if (foreThread != curThread && foreThread != 0) AttachThreadInput(curThread, foreThread, true); "
            "    if (targetThread != curThread && targetThread != 0) AttachThreadInput(curThread, targetThread, true); "
            "    keybd_event(0x12, 0, 0, 0); keybd_event(0x12, 0, 0x0002, 0); "
            "    ShowWindow(targetHwnd, 9); "
            "    ShowWindow(targetHwnd, 5); "
            "    BringWindowToTop(targetHwnd); "
            "    SetForegroundWindow(targetHwnd); "
            "    SwitchToThisWindow(targetHwnd, true); "
            "    SetWindowPos(targetHwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040); "
            "    SetWindowPos(targetHwnd, HWND_NOTOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040); "
            "    SetForegroundWindow(targetHwnd); "
            "    if (foreThread != curThread && foreThread != 0) AttachThreadInput(curThread, foreThread, false); "
            "    if (targetThread != curThread && targetThread != 0) AttachThreadInput(curThread, targetThread, false); "
            "  } "
            "  public static string ExecuteSwitch(int[] excludePids, string query) { "
            "    var list = new List<WInfo>(); "
            "    string[] systemBadTitles = new string[] { "
            "      \"windows input experience\", \"default ime\", \"msctfime ui\", \"gdi+ window\", "
            "      \"program manager\", \"textinputhost\", \"systemsettings\", \"cortana\", \"searchhost\", \"taskbar\" "
            "    }; "
            "    EnumWindows((h, lp) => { "
            "      if (!IsWindowVisible(h)) return true; "
            "      uint p; GetWindowThreadProcessId(h, out p); "
            "      StringBuilder sb = new StringBuilder(256); GetWindowText(h, sb, 256); "
            "      string t = sb.ToString().Trim(); "
            "      if (string.IsNullOrEmpty(t)) return true; "
            "      string tLow = t.ToLower(); "
            "      bool isSys = false; "
            "      foreach (var bad in systemBadTitles) { if (tLow.Contains(bad)) { isSys = true; break; } } "
            "      if (Array.IndexOf(excludePids, (int)p) < 0 && !isSys) { "
            "        string pname = \"\"; "
            "        try { pname = Process.GetProcessById((int)p).ProcessName.ToLower(); } catch {} "
            "        list.Add(new WInfo { Hwnd = h, Title = t, Pid = p, ProcName = pname }); "
            "      } "
            "      return true; "
            "    }, IntPtr.Zero); "
            "    if (list.Count == 0) return \"NONE|NONE\"; "
            "    string curTitle = list[0].Title; "
            "    WInfo targetWin = null; "
            "    string q = (query ?? \"\").ToLower().Trim(); "
            "    if (!string.IsNullOrEmpty(q)) { "
            "      foreach (var w in list) { "
            "        string t = w.Title.ToLower(); "
            "        string pn = w.ProcName.ToLower(); "
            "        if (t.Contains(q) || pn.Contains(q) "
            "            || (q == \"code\" && (pn.Contains(\"code\") || t.Contains(\"visual studio code\") || t.Contains(\"vscode\") || t.Contains(\" - code\"))) "
            "            || (q == \"visual studio code\" && (pn.Contains(\"code\") || t.Contains(\"visual studio code\") || t.Contains(\"vscode\") || t.Contains(\" - code\"))) "
            "            || (q == \"vscode\" && (pn.Contains(\"code\") || t.Contains(\"visual studio code\") || t.Contains(\"vscode\") || t.Contains(\" - code\"))) "
            "            || (q == \"chrome\" && (pn.Contains(\"chrome\") || t.Contains(\"chrome\") || t.Contains(\"google chrome\"))) "
            "            || (q == \"spotify\" && (pn.Contains(\"spotify\") || t.Contains(\"spotify\"))) "
            "            || (q == \"notepad\" && (pn.Contains(\"notepad\") || t.Contains(\"notepad\")))) { "
            "          targetWin = w; "
            "          break; "
            "        } "
            "      } "
            "      if (targetWin == null) { return \"NOT_FOUND|\" + q; } "
            "    } else { "
            "      targetWin = list.Count > 1 ? list[1] : list[0]; "
            "    } "
            "    ForceFocus(targetWin.Hwnd); "
            "    return curTitle + \"|\" + targetWin.Title; "
            "  } "
            "}'; "
            "[WSwitch]::ExecuteSwitch($excludePids, $targetQuery);"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=4.0,
            )
            out = (res.stdout or "").strip()
            if out.startswith("NOT_FOUND|"):
                return {"success": False, "error": f"Window '{target}' not found."}

            parts = out.split("|")
            from_win = parts[0] if len(parts) > 0 else "current window"
            to_win = parts[1] if len(parts) > 1 else from_win
            log.info("[COMPUTER_USE] Switched focus from '%s' to '%s'", from_win, to_win)
            return {"success": True, "from": from_win, "to": to_win, "message": f"Switched to {to_win}."}
        except Exception as e:
            log.warning("[COMPUTER_USE] Could not switch window: %s", e)
            return {"success": False, "error": str(e)}

    @classmethod
    def _get_protected_pids_csv(cls) -> str:
        """Returns comma-separated string of all Jarvis and UI process PIDs to protect from window manipulation."""
        pids = {os.getpid()}
        try:
            import psutil
            curr = psutil.Process(os.getpid())
            for ch in curr.children(recursive=True):
                pids.add(ch.pid)
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                cmd = " ".join(p.info.get('cmdline') or []).lower()
                if "ui_window" in cmd or "jarvis.py" in cmd or "pywebview" in cmd:
                    pids.add(p.info['pid'])
        except Exception:
            pass
        return ",".join(str(p) for p in pids)

    @classmethod
    def close_window(cls, app_name: str | None = None) -> dict[str, Any]:
        """Close the currently active window (WM_CLOSE) or a specific application."""
        if sys.platform != "win32":
            return {"success": False, "error": "close_window is only supported on Windows."}

        target = (app_name or "").strip().lower()
        if target and target not in ("current", "active", "this", "window", "cua so", "cửa sổ"):
            proc_map = {
                "chrome": "chrome",
                "google chrome": "chrome",
                "browser": "chrome",
                "vscode": "Code",
                "vs code": "Code",
                "code": "Code",
                "antigravity": "Antigravity",
                "cursor": "Cursor",
                "spotify": "Spotify",
                "discord": "Discord",
                "notepad": "notepad",
                "docker desktop": "Docker Desktop",
                "docker": "Docker Desktop",
            }
            proc_name = proc_map.get(target, target).lower()
            try:
                import psutil
                killed = 0
                for p in psutil.process_iter(['pid', 'name']):
                    pname = (p.info.get('name') or "").lower()
                    if proc_name in pname or (proc_name == "docker desktop" and "docker" in pname):
                        p.terminate()
                        killed += 1
                if killed > 0:
                    log.info("[COMPUTER_USE] Closed application: '%s' (%d processes)", target, killed)
                    return {"success": True, "message": f"Closed {target}."}
            except Exception as e:
                log.warning("[COMPUTER_USE] Process terminate error: %s", e)

        # Close active user application window via Native Win32 PostMessage WM_CLOSE
        try:
            import win32gui
            import win32process
            import win32con
            protected_pids = cls._get_protected_pids_csv().split(",")
            protected_set = {int(p.strip()) for p in protected_pids if p.strip().isdigit()}

            system_bad_titles = (
                "windows input experience", "default ime", "msctfime ui", "gdi+ window",
                "program manager", "textinputhost", "systemsettings", "cortana", "searchhost", "taskbar"
            )

            # Check current foreground window first
            fg = win32gui.GetForegroundWindow()
            if fg and win32gui.IsWindowVisible(fg):
                _, pid = win32process.GetWindowThreadProcessId(fg)
                t = win32gui.GetWindowText(fg).strip().lower()
                if pid not in protected_set and not any(b in t for b in system_bad_titles):
                    win32gui.PostMessage(fg, win32con.WM_CLOSE, 0, 0)
                    log.info("[COMPUTER_USE] Closed active foreground window '%s' (HWND: %s)", t, fg)
                    return {"success": True, "message": "Closed current window."}

            # Otherwise find top user window
            cand_hwnd = 0
            cand_title = ""
            def _enum(hwnd, _):
                nonlocal cand_hwnd, cand_title
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                t = win32gui.GetWindowText(hwnd).strip()
                if not t:
                    return True
                t_low = t.lower()
                if any(b in t_low for b in system_bad_titles):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in protected_set:
                    return True
                cand_hwnd = hwnd
                cand_title = t
                return False  # Stop enumeration

            win32gui.EnumWindows(_enum, None)
            if cand_hwnd:
                win32gui.PostMessage(cand_hwnd, win32con.WM_CLOSE, 0, 0)
                log.info("[COMPUTER_USE] Closed active user window '%s' (HWND: %s)", cand_title, cand_hwnd)
                return {"success": True, "message": f"Closed {cand_title}."}
        except Exception as e:
            log.warning("[COMPUTER_USE] Native close window error: %s", e)

        return {"success": True, "message": "Closed current window."}

    @classmethod
    def minimize_window(cls) -> dict[str, Any]:
        """Minimize the active user application window (preserving Jarvis UI)."""
        if sys.platform != "win32":
            return {"success": False, "error": "minimize_window is only supported on Windows."}
        try:
            import win32gui
            import win32process
            import win32con
            protected_pids = cls._get_protected_pids_csv().split(",")
            protected_set = {int(p.strip()) for p in protected_pids if p.strip().isdigit()}

            system_bad_titles = (
                "windows input experience", "default ime", "msctfime ui", "gdi+ window",
                "program manager", "textinputhost", "systemsettings", "cortana", "searchhost", "taskbar"
            )

            fg = win32gui.GetForegroundWindow()
            if fg and win32gui.IsWindowVisible(fg):
                _, pid = win32process.GetWindowThreadProcessId(fg)
                t = win32gui.GetWindowText(fg).strip().lower()
                if pid not in protected_set and not any(b in t for b in system_bad_titles):
                    win32gui.ShowWindow(fg, win32con.SW_MINIMIZE)
                    log.info("[COMPUTER_USE] Minimized active foreground window '%s'", t)
                    return {"success": True, "message": "Minimized window."}

            cand_hwnd = 0
            def _enum(hwnd, _):
                nonlocal cand_hwnd
                if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                    return True
                t = win32gui.GetWindowText(hwnd).strip()
                if not t:
                    return True
                t_low = t.lower()
                if any(b in t_low for b in system_bad_titles):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in protected_set:
                    return True
                cand_hwnd = hwnd
                return False

            win32gui.EnumWindows(_enum, None)
            if cand_hwnd:
                win32gui.ShowWindow(cand_hwnd, win32con.SW_MINIMIZE)
                log.info("[COMPUTER_USE] Minimized user window (HWND: %s)", cand_hwnd)
                return {"success": True, "message": "Minimized window."}
        except Exception as e:
            log.warning("[COMPUTER_USE] Native minimize error: %s", e)

        return {"success": True, "message": "Minimized window."}

    @classmethod
    def maximize_window(cls) -> dict[str, Any]:
        """Maximize the active user application window (preserving Jarvis UI)."""
        if sys.platform != "win32":
            return {"success": False, "error": "maximize_window is only supported on Windows."}
        try:
            import win32gui
            import win32process
            import win32con
            protected_pids = cls._get_protected_pids_csv().split(",")
            protected_set = {int(p.strip()) for p in protected_pids if p.strip().isdigit()}

            system_bad_titles = (
                "windows input experience", "default ime", "msctfime ui", "gdi+ window",
                "program manager", "textinputhost", "systemsettings", "cortana", "searchhost", "taskbar"
            )

            fg = win32gui.GetForegroundWindow()
            if fg and win32gui.IsWindowVisible(fg):
                _, pid = win32process.GetWindowThreadProcessId(fg)
                t = win32gui.GetWindowText(fg).strip().lower()
                if pid not in protected_set and not any(b in t for b in system_bad_titles):
                    win32gui.ShowWindow(fg, win32con.SW_MAXIMIZE)
                    log.info("[COMPUTER_USE] Maximized active foreground window '%s'", t)
                    return {"success": True, "message": "Maximized window."}

            cand_hwnd = 0
            def _enum(hwnd, _):
                nonlocal cand_hwnd
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                t = win32gui.GetWindowText(hwnd).strip()
                if not t:
                    return True
                t_low = t.lower()
                if any(b in t_low for b in system_bad_titles):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in protected_set:
                    return True
                cand_hwnd = hwnd
                return False

            win32gui.EnumWindows(_enum, None)
            if cand_hwnd:
                win32gui.ShowWindow(cand_hwnd, win32con.SW_MAXIMIZE)
                log.info("[COMPUTER_USE] Maximized user window (HWND: %s)", cand_hwnd)
                return {"success": True, "message": "Maximized window."}
        except Exception as e:
            log.warning("[COMPUTER_USE] Native maximize error: %s", e)

        return {"success": True, "message": "Maximized window."}

    @classmethod
    def click_coordinate(cls, x_ratio: float, y_ratio: float, click_count: int = 1) -> dict[str, Any]:
        """
        Click at a relative coordinate (0.0 to 1.0) within the active foreground window.
        """
        if sys.platform != "win32" or not user32:
            return {"success": False, "error": "click_coordinate is only supported on Windows."}

        try:
            hwnd = user32.GetForegroundWindow()
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w <= 0 or h <= 0:
                sw = user32.GetSystemMetrics(0)
                sh = user32.GetSystemMetrics(1)
                tx = int(sw * x_ratio)
                ty = int(sh * y_ratio)
            else:
                tx = int(rect.left + w * x_ratio)
                ty = int(rect.top + h * y_ratio)

            user32.SetCursorPos(tx, ty)
            time.sleep(0.05)
            for _ in range(click_count):
                user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
                time.sleep(0.05)
                user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
                time.sleep(0.05)

            log.info("[COMPUTER_USE] Clicked at relative (%s, %s) -> Screen (%d, %d)", x_ratio, y_ratio, tx, ty)
            return {"success": True, "message": f"Clicked at ({tx}, {ty})"}
        except Exception as e:
            log.warning("[COMPUTER_USE] Failed to click coordinate: %s", e)
            return {"success": False, "error": str(e)}

    @classmethod
    def scroll_page(cls, direction: str = "down", amount: int = 6) -> dict[str, Any]:
        """
        Scroll or roll the active window/page up or down.
        direction: 'down', 'up', 'top', 'bottom'
        amount: number of mouse wheel notches (default 6)
        """
        if sys.platform != "win32":
            return {"success": False, "error": "scroll_page is only supported on Windows."}

        dir_clean = (direction or "down").strip().lower()
        try:
            user32 = ctypes.windll.user32
            # Check if scrolling to absolute top or bottom
            if dir_clean in ("top", "đầu trang", "dau trang", "lên đầu", "len dau", "về đầu trang", "ve dau trang"):
                user32.keybd_event(0x24, 0, 0, 0)  # VK_HOME
                time.sleep(0.05)
                user32.keybd_event(0x24, 0, 0x0002, 0)
                log.info("[COMPUTER_USE] Scrolled to top of page.")
                return {"success": True, "message": "Scrolled to top of page."}
            elif dir_clean in ("bottom", "cuối trang", "cuoi trang", "xuống cuối", "xuong cuoi", "về cuối trang", "ve cuoi trang"):
                user32.keybd_event(0x23, 0, 0, 0)  # VK_END
                time.sleep(0.05)
                user32.keybd_event(0x23, 0, 0x0002, 0)
                log.info("[COMPUTER_USE] Scrolled to bottom of page.")
                return {"success": True, "message": "Scrolled to bottom of page."}

            # Standard smooth mouse wheel scroll
            # MOUSEEVENTF_WHEEL = 0x0800
            # Delta: +120 (up), -120 (down)
            is_up = dir_clean in ("up", "lên", "len", "trên", "tren", "roll up", "scroll up", "lên trên", "len tren")
            delta_per_notch = 120
            wheel_delta = delta_per_notch if is_up else -delta_per_notch
            notches = max(1, min(20, amount))

            for _ in range(notches):
                user32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(wheel_delta).value, 0)
                time.sleep(0.02)

            action_desc = "up" if is_up else "down"
            log.info("[COMPUTER_USE] Scrolled %s (%d notches)", action_desc, notches)
            return {"success": True, "message": f"Scrolled {action_desc}."}
        except Exception as e:
            log.warning("[COMPUTER_USE] Failed to scroll page: %s", e)
            return {"success": False, "error": str(e)}

    @classmethod
    def click_entity(cls, entity_name: str, app_name: str = "chrome") -> dict[str, Any]:
        """
        Recognize and click an entity in an application window.
        Supported entities: 'video_1', 'video_2', 'video_3', 'video_4', 'search_bar', 'play', 'fullscreen', 'mute'.
        """
        cls.switch_window(app_name)
        time.sleep(0.4)

        ent = entity_name.lower().strip()
        entity_coords = {
            "video_1": (0.35, 0.45),
            "video 1": (0.35, 0.45),
            "first_video": (0.35, 0.45),
            "first video": (0.35, 0.45),
            "video_2": (0.72, 0.45),
            "video 2": (0.72, 0.45),
            "second_video": (0.72, 0.45),
            "second video": (0.72, 0.45),
            "video_3": (0.35, 0.80),
            "video 3": (0.35, 0.80),
            "third_video": (0.35, 0.80),
            "third video": (0.35, 0.80),
            "video_4": (0.72, 0.80),
            "video 4": (0.72, 0.80),
            "search_bar": (0.48, 0.16),
            "search": (0.48, 0.16),
        }

        if ent in ("play", "pause", "play_pause"):
            return cls.press_hotkey("k")
        elif ent in ("fullscreen", "toan man hinh"):
            return cls.press_hotkey("f")
        elif ent in ("mute", "unmute", "tat tieng"):
            return cls.press_hotkey("m")

        if ent in entity_coords:
            xr, yr = entity_coords[ent]
            return cls.click_coordinate(xr, yr)

    @classmethod
    def wait_for_page_ready(cls, wait_seconds: float = 2.5) -> None:
        """
        Wait for browser web page DOM, video thumbnails, and scripts to settle.
        Dismisses any modal/translate popups using Escape.
        """
        time.sleep(wait_seconds)
        # Dismiss any Google Translate / overlay popup with Escape key
        try:
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                # Send ESC keydown & keyup (VK_ESCAPE = 0x1B)
                user32.keybd_event(0x1B, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(0x1B, 0, 0x0002, 0)
                time.sleep(0.1)
        except Exception as e:
            log.debug("[COMPUTER_USE] Popup dismissal error: %s", e)

    @classmethod
    def resolve_and_click_target(
        cls,
        query: str,
        action: str = "open",
        app_name: str = "chrome",
        wait_load: bool = True,
    ) -> dict[str, Any]:
        """
        Use Hermes UI Perception & Targeting Engine to perceive active window,
        resolve user target query (ordinals, rows/cols, text, relative positions, composite sub-components),
        and safely click the resolved interaction point.
        """
        if app_name:
            cls.switch_window(app_name)
        if wait_load:
            cls.wait_for_page_ready(wait_seconds=1.5)

        try:
            from ..ui_perception.models import ActionType, ResolutionStatus
            from ..ui_perception.service import get_ui_service

            act_type = ActionType.OPEN_MENU if "menu" in action.lower() or "ba chấm" in query.lower() else ActionType.OPEN
            ui_service = get_ui_service()

            res, verif = ui_service.interact_with_target(
                query=query,
                action=act_type,
                click_callback=lambda px, py, nx, ny: cls.click_coordinate(nx, ny, click_count=1),
            )

            if res.is_success():
                return {
                    "success": True,
                    "status": res.status.value,
                    "target_id": res.target_element.id if res.target_element else None,
                    "confidence": res.confidence,
                    "interaction_point": res.interaction_point.to_dict() if res.interaction_point else None,
                    "verified": verif.success if verif else True,
                    "message": f"Successfully interacted with target '{query}'.",
                }
            else:
                return {
                    "success": False,
                    "status": res.status.value,
                    "error": res.error_message,
                    "suggested_action": res.suggested_action,
                }
        except Exception as e:
            log.warning("[COMPUTER_USE] UI targeting resolution error: %s", e)
            return {"success": False, "error": str(e)}

    @classmethod
    def select_youtube_video(cls, index: int = 1, wait_load: bool = True) -> dict[str, Any]:
        """
        Select or play the N-th video on a YouTube page using direct entity recognition & clicking.
        Includes smart load-wait synchronization, popup dismissal, and UI Perception Engine integration.
        """
        cls.switch_window("chrome")
        if wait_load:
            log.info("[COMPUTER_USE] Waiting for YouTube page & video grid to settle...")
            cls.wait_for_page_ready(wait_seconds=2.5)
        else:
            time.sleep(0.4)

        # 1. Try resolving via Hermes UI Perception Service if active
        try:
            from ..ui_perception.models import ActionType, ResolutionStatus
            from ..ui_perception.service import get_ui_service

            ui_service = get_ui_service()
            tree = ui_service.perceive_active_window()
            if tree and len(tree.elements) > 0:
                res = ui_service.resolve_target(f"video thứ {index}", tree=tree, action=ActionType.OPEN)
                if res.is_success() and res.interaction_point:
                    pt = res.interaction_point
                    log.info("[COMPUTER_USE] UI Service resolved video %d -> Normalized (%.3f, %.3f)", index, pt.normalized_x, pt.normalized_y)
                    return cls.click_coordinate(pt.normalized_x, pt.normalized_y, click_count=2)
        except Exception as e:
            log.debug("[COMPUTER_USE] Fast-path coordinate fallback: %s", e)

        # 2. Entity coordinates fallback for YouTube grid items (support indices 1 to 12)
        coords_map = {
            1: (0.35, 0.45),
            2: (0.72, 0.45),
            3: (0.35, 0.78),
            4: (0.72, 0.78),
            5: (0.35, 0.95),
            6: (0.72, 0.95),
        }
        if index in coords_map:
            xr, yr = coords_map[index]
        else:
            col = (index - 1) % 2
            row = (index - 1) // 2
            xr = 0.35 if col == 0 else 0.72
            yr = min(0.95, 0.45 + row * 0.33)

        res = cls.click_coordinate(xr, yr, click_count=2)
        time.sleep(0.3)

        # Send Enter to guarantee navigation
        try:
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                user32.keybd_event(0x0D, 0, 0, 0)  # VK_RETURN
                time.sleep(0.05)
                user32.keybd_event(0x0D, 0, 0x0002, 0)
        except Exception:
            pass

        return {"success": True, "message": f"Clicked and played YouTube video {index}."}

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
